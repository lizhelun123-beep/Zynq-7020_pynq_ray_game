source [file join [file dirname [info script]] .. common.tcl]
if {$stage ni {prepare csim synth ip}} {error "HLS stage must be prepare/csim/synth/ip"}
foreach command {open_project open_solution config_export export_design} {
    if {![llength [info commands $command]]} {error "Unsupported HLS Tcl API: $command"}
}
set project [file join $DEMO_BUILD hls]
if {$stage eq "prepare"} {
    if {[file exists $project]} {error "HLS output exists;do not reset old projects"}
    open_project $project
    set_top add_bias
    add_files [file join $DEMO_SOURCE hls add_bias.cpp]
    add_files -tb [file join $DEMO_SOURCE hls testbench.cpp]
    open_solution solution -flow_target vivado
    set_part $DEMO_PART
    create_clock -period [expr {1000.0 / $DEMO_CLOCK_MHZ}] -name default
    config_export -format ip_catalog -rtl verilog -vendor example.org -library hls -version 1.0
    mark_stage hls_prepare
} else {
    require_stage hls_prepare
    open_project $project
    open_solution solution
    if {$stage eq "csim"} {
        csim_design
        mark_stage hls_csim
    } elseif {$stage eq "synth"} {
        require_stage hls_csim
        csynth_design
        mark_stage hls_synth
    } else {
        require_stage hls_synth
        export_design -format ip_catalog -rtl verilog
        mark_stage hls_ip
    }
}
close_project
exit
