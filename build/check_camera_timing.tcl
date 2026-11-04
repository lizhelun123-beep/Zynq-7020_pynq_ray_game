# Fixed-route camera-model reanalysis only. No synthesis, implementation,
# IDELAY edits, checkpoint save, hardware export or device access.
if {$argc != 3} {error "Usage: check_camera_timing.tcl existing_routed.dcp corrected_system.xdc fresh_output"}
if {![string match {2023.1*} [version -short]]} {error "Vivado 2023.1 required"}
set checkpoint [file normalize [lindex $argv 0]]
set model_xdc [file normalize [lindex $argv 1]]
set out [file normalize [lindex $argv 2]]
if {![file isfile $checkpoint] || ![file isfile $model_xdc]} {error "Missing checkpoint or model"}
if {[file exists $out]} {error "Preserve existing analysis output: $out"}
file mkdir $out
set stage open_checkpoint
set code [catch {
    open_checkpoint $checkpoint
    set ports [get_ports {dphy_data_hs_p[*] dphy_data_hs_n[*]}]
    set endpoints [lsort [get_pins -hier -filter {REF_PIN_NAME == DDLY && NAME =~ *HSDeserializerX/Deserializer/DDLY}]]
    set data_delays [lsort [get_cells -hier -filter {REF_NAME == IDELAYE2 && NAME =~ *HSDeserializerX/*InputDelay}]]
    set clock_delays [get_cells -hier -filter {REF_NAME == IDELAYE2 && NAME =~ *ClockLane/HSClockingX/*InputDelay}]
    if {[llength $ports] != 4 || [llength $endpoints] != 2 ||
        [llength $data_delays] != 2 || [llength $clock_delays] != 1} {
        error "Expected two lanes, four differential data ports and three IDELAYs"
    }
    set fixed_settings {}
    set receipt [open [file join $out fixed_route_scope.txt] w]
    puts $receipt "Existing checkpoint: $checkpoint"
    puts $receipt "Corrected model: $model_xdc"
    puts $receipt "Scope: same routed netlist; replace only camera input clock/window in memory."
    puts $receipt "Other historical checkpoint constraints remain; this is not a clean corrected-source build."
    puts $receipt "No current-boot physical frequency, pin-eye or deployed-Overlay timing signoff."
    foreach cell [concat $clock_delays $data_delays] {
        lappend fixed_settings [list $cell [get_property IDELAY_VALUE $cell] [get_property LOC $cell]]
    }
    puts $receipt "Original fixed IDELAY values and locations: $fixed_settings"
    close $receipt
    report_clocks -file [file join $out clocks_before.rpt]
    set stage apply_camera_model
    # The first rising-edge min/max commands omit -add_delay, replacing the
    # old delay sets. Falling-edge constraints are then explicitly added.
    read_xdc $model_xdc
    update_timing
    set period [get_property PERIOD [get_clocks mipi_hs_clk]]
    if {abs($period - 7.143) > 0.000001} {error "Corrected HS140MHz clock was not applied on the 1ps tool grid"}
    report_clocks -file [file join $out clocks_after.rpt]
    write_xdc -type timing -force [file join $out effective_timing_after.xdc]
    report_timing_summary -delay_type min_max -report_unconstrained -file [file join $out timing_after.rpt]
    set stage sampling_paths
    set rows [open [file join $out sampling_paths.tsv] w]
    puts $rows "lane\tpolarity\tcorner\tdata_transition\tdelay_type\tpath_count\tworst_slack_ns"
    set detail [file join $out sampling_paths.rpt]
    set queries 0
    set worst_setup Inf
    set worst_hold Inf
    foreach endpoint $endpoints {
        if {![regexp {DataLaneGen\[([01])\]} $endpoint unused lane]} {error "Unknown lane endpoint: $endpoint"}
        foreach polarity {p n} {
            set port [get_ports -regexp [format {^dphy_data_hs_%s\[%d\]$} $polarity $lane]]
            if {[llength $port] != 1} {error "Missing lane source"}
            foreach corner {Fast Slow} {
                foreach transition {rise fall} {
                    foreach type {max min} {
                        set paths [get_timing_paths -from $port -${transition}_to $endpoint -corner $corner -delay_type $type -max_paths 8 -nworst 8]
                        if {[llength $paths] == 0} {error "Missing $lane/$polarity/$corner/$transition/$type paths"}
                        set slacks {}
                        foreach path $paths {lappend slacks [get_property SLACK $path]}
                        set worst [lindex [lsort -real $slacks] 0]
                        if {$type eq {max}} {set worst_setup [expr {min($worst_setup, $worst)}]}
                        if {$type eq {min}} {set worst_hold [expr {min($worst_hold, $worst)}]}
                        puts $rows "$lane\t$polarity\t$corner\t$transition\t$type\t[llength $paths]\t$worst"
                        report_timing -from $port -${transition}_to $endpoint -corner $corner -delay_type $type -max_paths 8 -nworst 8 -significant_digits 3 -path_type full_clock_expanded -append -file $detail
                        incr queries
                    }
                }
            }
        }
    }
    close $rows
    set current_settings {}
    foreach cell [concat $clock_delays $data_delays] {
        lappend current_settings [list $cell [get_property IDELAY_VALUE $cell] [get_property LOC $cell]]
    }
    if {$current_settings ne $fixed_settings || $queries != 32} {error "Fixed-setting/query coverage invariant failed"}
    set summary [open [file join $out sampling_summary.tsv] w]
    puts $summary "metric\tvalue"
    puts $summary "sampling_setup_ns\t$worst_setup"
    puts $summary "sampling_hold_ns\t$worst_hold"
    puts $summary "covered_queries\t$queries"
    puts $summary "fixed_IDELAY_and_locations\tUNCHANGED"
    puts $summary "timing_status\t[expr {$worst_setup >= 0 && $worst_hold >= 0 ? {PASS_UNDER_DECLARED_MODEL} : {FAIL}}]"
    close $summary
    close_design
    set stage complete
} message details]
set result [open [file join $out status.tsv] w]
puts $result "stage\tresult"
puts $result "$stage\t[expr {$code ? {ANALYSIS_FAILED} : {ANALYZED}}]"
close $result
if {$code} {return -options $details $message}
puts "CAMERA_MODEL_ANALYZED: setup=$worst_setup hold=$worst_hold; fixed routed checkpoint only; no hardware export"
