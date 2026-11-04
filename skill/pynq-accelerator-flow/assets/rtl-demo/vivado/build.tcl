# Batch only. Host run_rtl.py verifies frozen inputs before invoking this file.
if {$argc != 2} {error "Expected config.tcl and one stage"}
source -encoding utf-8 [file normalize [lindex $argv 0]]
set stage [lindex $argv 1]
if {[version -short] ne $DEMO_TOOL_VERSION} {error "Tool release differs from profile"}
set project_dir [file join $DEMO_BUILD project]
file mkdir [file join $DEMO_BUILD reports]
proc require_file {path} {if {![file isfile $path]} {error "Missing prerequisite: $path"}}
proc stamp {name text} {
    global DEMO_BUILD
    set f [open [file join $DEMO_BUILD "$name.txt"] w];puts $f $text;close $f
}
switch -- $stage {
    sim {
        create_project sim [file join $DEMO_BUILD sim] -part $DEMO_PART
        add_files -norecurse [file join $DEMO_SOURCE hdl add32.v]
        add_files -fileset sim_1 -norecurse [file join $DEMO_SOURCE sim add32_tb.sv]
        set_property top add32_tb [get_filesets sim_1]
        set_property xsim.simulate.runtime all [get_filesets sim_1]
        launch_simulation -simset sim_1 -mode behavioral
        close_sim
    }
    prepare {
        source -encoding utf-8 [file join $DEMO_SOURCE vivado project.tcl]
        make_project $project_dir $DEMO_PS_PRESET $DEMO_PART $DEMO_CLOCK_MHZ
        if {[get_property TOP [current_fileset]] ne "system_wrapper"} {error "Wrong production top"}
        set rows [list "tool\t[version -short]" "part\t[get_property PART [current_project]]" "top\tsystem_wrapper"]
        foreach {pattern offset range} {*add32_0* 0x43c00000 4096 *axi_intc* 0x41800000 65536} {
            set segment [get_bd_addr_segs -of_objects [get_bd_addr_spaces ps7/Data] -filter "NAME =~ $pattern"]
            if {[llength $segment] != 1 || [get_property OFFSET $segment] != $offset || [get_property RANGE $segment] != $range} {error "Address contract differs: $pattern"}
        }
        foreach {source sink} {ps7/FCLK_CLK0 add32_0/s_axi_aclk rst/peripheral_aresetn add32_0/s_axi_aresetn add32_0/interrupt axi_intc/intr axi_intc/irq ps7/IRQ_F2P} {
            set left [get_bd_nets -of_objects [get_bd_pins $source]]
            set right [get_bd_nets -of_objects [get_bd_pins $sink]]
            if {[llength $left]!=1 || $left ne $right} {error "Missing connection: $source -> $sink"}
        }
        set frequency [get_property CONFIG.PCW_FPGA0_PERIPHERAL_FREQMHZ [get_bd_cells ps7]]
        lappend rows "requested_fclk_mhz\t$frequency"
        if {abs($frequency-$DEMO_CLOCK_MHZ)>0.001} {error "FCLK request differs"}
        stamp prepare [join $rows \n]
    }
    synth {
        require_file [file join $DEMO_BUILD prepare.txt]
        require_file [file join $DEMO_BUILD sim_pass.json]
        open_project [file join $project_dir add32.xpr]
        # One top-level run;BD output products may have their own IP OOC runs.
        launch_runs synth_1 -jobs 4
        wait_on_run synth_1
        if {[get_property STATUS [get_runs synth_1]] ne "synth_design Complete!"} {error "Synthesis did not complete"}
        open_run synth_1
        report_utilization -file [file join $DEMO_BUILD reports synth_utilization.rpt]
        stamp synth "PASS"
    }
    impl {
        require_file [file join $DEMO_BUILD synth.txt]
        open_project [file join $project_dir add32.xpr]
        launch_runs impl_1 -to_step route_design -jobs 4
        wait_on_run impl_1
        if {[get_property STATUS [get_runs impl_1]] ne "route_design Complete!"} {error "Implementation did not complete"}
        open_run impl_1
        set report_dir [file join $DEMO_BUILD reports]
        report_timing_summary -delay_type min_max -check_timing_verbose -file [file join $report_dir timing.rpt]
        report_cdc -details -no_waiver -file [file join $report_dir cdc.rpt]
        report_drc -file [file join $report_dir drc.rpt]
        report_utilization -file [file join $report_dir utilization.rpt]
        report_clocks -file [file join $report_dir clocks.rpt]
        set rows {}
        foreach key {WNS TNS WHS THS} {lappend rows "$key\t[get_property STATS.$key [get_runs impl_1]]"}
        foreach {key severity} {drc_errors Error drc_critical {Critical Warning}} {
            set count 0
            foreach violation [get_drc_violations -quiet] {
                if {[get_property SEVERITY $violation] eq $severity} {incr count}
            }
            lappend rows "$key\t$count"
        }
        stamp impl [join $rows \n]
    }
    export {
        # Host verifies report gate immediately before this native invocation.
        require_file [file join $DEMO_BUILD gate.json]
        open_project [file join $project_dir add32.xpr]
        open_run impl_1
        file mkdir [file join $DEMO_BUILD export]
        write_bitstream [file join $project_dir add32.runs impl_1 system_wrapper.bit]
        write_hw_platform -fixed -include_bit -file [file join $DEMO_BUILD export system.xsa]
        stamp export "PASS"
    }
    default {error "Unknown stage $stage"}
}
# XSim can close the inherited stdout channel on Windows. A dedicated receipt
# records reaching this point;do not make native success depend on console I/O.
stamp "${stage}_native_pass" $stage
