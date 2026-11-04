# Run on the private input copy made by run_pl.py, never on board/runtime.
if {$argc < 2 || $argc > 3} {error "Usage: build_pl.tcl staged_project fresh_output ?validate-only|reports-only?"}
set root [file normalize [lindex $argv 0]]
set out [file normalize [lindex $argv 1]]
set validate_only [expr {$argc == 3 && [lindex $argv 2] eq {validate-only}}]
set reports_only [expr {$argc == 3 && [lindex $argv 2] eq {reports-only}}]
if {$argc == 3 && !$validate_only && !$reports_only} {error "Unknown build mode: [lindex $argv 2]"}
if {[file exists $out]} {error "Output already exists: $out"}
if {![string match "2023.1*" [version -short]]} {error "Vivado 2023.1 required"}
set bd [file join $root color_test color_test.srcs sources_1 bd system system.bd]
if {![file isfile $bd]} {error "Missing staged block design: $bd"}
file mkdir $out
set stage prepare

# Keep Vivado's lazy BD/IP Tcl initialization in the global frame. Wrapping
# these commands in a proc changes the scope used by vendor source callbacks:
# first-time module_ref XGUI loading can then fail although the file is created.
# A global catch records failures without introducing a local procedure frame.
set code [catch {
    set reports [file join $out reports]
    set checkpoints [file join $out checkpoints]
    set artifacts [file join $out artifacts]
    file mkdir $reports $checkpoints
    # The staged XPR is the single input definition, including its implementation
    # constraints. Do not create a second project with a different XDC list.
    open_project [file join $root color_test color_test.xpr]
    set_property ip_repo_paths [list [file join $root color_test repo ip]] [current_project]
    set_property XPM_LIBRARIES {XPM_CDC XPM_FIFO XPM_MEMORY} [current_project]
    update_ip_catalog -rebuild
    reset_run synth_1
    update_compile_order -fileset sources_1
    set stage open_block_design
    open_bd_design $bd
    set stage module_references
    set references [get_ips -quiet -filter {IPDEF =~ xilinx.com:module_ref:*}]
    if {[llength $references]} {update_module_reference $references}
    validate_bd_design
    save_bd_design
    write_bd_tcl -force [file join $out prepared_bd.tcl]
    set stage generate_targets
    generate_target all [get_files $bd]
    add_files -norecurse [make_wrapper -files [get_files $bd] -top]
    set_property top system_wrapper [current_fileset]
    update_compile_order -fileset sources_1
    report_ip_status -file [file join $reports ip_status.rpt]
    report_compile_order -used_in synthesis -file [file join $reports compile_order.rpt]
    if {$validate_only} {
        close_project
        set stage validated
    } else {
        set stage synthesis
        launch_runs synth_1 -jobs 2
        wait_on_run synth_1
        if {![string match "synth_design Complete*" [get_property STATUS [get_runs synth_1]]]} {
            error "Synthesis failed"
        }
        open_run synth_1
        write_checkpoint -force [file join $checkpoints synthesized.dcp]
        report_timing_summary -delay_type min_max -report_unconstrained -file [file join $reports post_synth_timing.rpt]
        report_utilization -file [file join $reports post_synth_utilization.rpt]
        close_design

        set stage implementation
        launch_runs impl_1 -to_step route_design -jobs 2
        wait_on_run impl_1
        if {![string match "route_design Complete*" [get_property STATUS [get_runs impl_1]]]} {
            error "Implementation failed"
        }
        open_run impl_1
        write_checkpoint -force [file join $checkpoints routed.dcp]
        write_xdc -force [file join $out effective_constraints.xdc]
        report_timing_summary -delay_type min_max -report_unconstrained -file [file join $reports post_impl_timing.rpt]
        report_utilization -file [file join $reports post_impl_utilization.rpt]
        report_clock_interaction -file [file join $reports post_impl_clock_interaction.rpt]
        report_cdc -details -file [file join $reports post_impl_cdc.rpt]
        report_drc -file [file join $reports post_impl_drc.rpt]
        report_methodology -file [file join $reports post_impl_methodology.rpt]

        set stage timing_gate
        set summary [open [file join $reports timing_gate.tsv] w]
        puts $summary "delay_type\tworst_slack_ns"
        set failed {}
        foreach delay {max min} {
            set paths [get_timing_paths -delay_type $delay -max_paths 1]
            if {[llength $paths] != 1} {
                puts $summary "$delay\tNO_PATH"
                lappend failed "${delay}: no timing path"
            } else {
                set slack [get_property SLACK [lindex $paths 0]]
                puts $summary "$delay\t$slack"
                if {$slack < 0} {lappend failed "${delay}: slack=$slack"}
            }
        }
        close $summary
        set timing_file [open [file join $reports post_impl_timing.rpt] r]
        set timing_text [read $timing_file]
        close $timing_file
        if {[string first {All user specified timing constraints are met.} $timing_text] < 0} {
            lappend failed {Timing summary does not confirm all user timing constraints}
        }
        set timing_status [expr {[llength $failed] ? {FAIL} : {PASS}}]
        set result_file [open [file join $reports timing_result.tsv] w]
        puts $result_file "status\tdetail"
        puts $result_file "$timing_status\t[join $failed {; }]"
        close $result_file
        if {$reports_only} {
            close_project
            set stage reports_complete
        } else {
            if {[llength $failed]} {error "Timing failed: [join $failed {; }]"}
            close_design

            set stage bitstream
            launch_runs impl_1 -to_step write_bitstream -jobs 2
            wait_on_run impl_1
            if {![string match "write_bitstream Complete*" [get_property STATUS [get_runs impl_1]]]} {
                error "Bitstream generation failed"
            }
            open_run impl_1
            set run_bit [file join [get_property DIRECTORY [get_runs impl_1]] system_wrapper.bit]
            if {![file isfile $run_bit]} {error "Missing bitstream from this run"}
            file mkdir $artifacts
            file copy $run_bit [file join $artifacts system_wrapper.bit]
            set stage export
            write_hw_platform -fixed -include_bit -force [file join $artifacts system_wrapper.xsa]
            close_project
            set stage complete
        }
    }
} message details]

set status [open [file join $out status.tsv] w]
puts $status "stage\tresult"
set result [expr {$code ? {FAILED} : ($validate_only ? {VALIDATED_INPUTS} : ($reports_only ? {REPORTS_COMPLETE} : {EXPORTED_CANDIDATE}))}]
puts $status "$stage\t$result"
close $status
if {$code} {return -options $details $message}
if {$validate_only} {
    puts "PL_VALIDATED_INPUTS: BD/module references/output products only; synthesis and implementation NOT_RUN"
} elseif {$reports_only} {
    puts "PL_REPORTS_COMPLETE: timing=$timing_status; no BIT/XSA export or deployed-Overlay signoff"
} else {
    puts "PL_EXPORTED_CANDIDATE: no board qualification; inspect CDC/DRC and the Python build record"
}
