# Reanalyze a new zero-clock-IDELAY routed candidate. No saved DCP or export.
if {$argc != 2} {error {Usage: check_sampling_window.tcl routed.dcp fresh_output}}
if {![string match {2023.1*} [version -short]]} {error {Vivado 2023.1 required}}
set dcp [file normalize [lindex $argv 0]]
set out [file normalize [lindex $argv 1]]
if {[file exists $out]} {error {Preserve existing output}}
file mkdir $out
open_checkpoint $dcp
set ports [get_ports {dphy_data_hs_p[*] dphy_data_hs_n[*]}]
set endpoints [lsort [get_pins -hier -filter {REF_PIN_NAME == DDLY && NAME =~ *HSDeserializerX/Deserializer/DDLY}]]
set data [get_cells -hier -filter {REF_NAME == IDELAYE2 && NAME =~ *HSDeserializerX/*InputDelay}]
set clock [get_cells -hier -filter {REF_NAME == IDELAYE2 && NAME =~ *ClockLane/HSClockingX/*InputDelay}]
if {[llength $ports] != 4 || [llength $endpoints] != 2 || [llength $data] != 2 || [llength $clock] != 0} {
    error {Expected two data IDELAYs and zero clock IDELAYs}
}
if {abs([get_property PERIOD [get_clocks mipi_hs_clk]]-7.143) > 0.000001} {error {Unexpected input clock}}
set fixed {}
foreach cell $data {lappend fixed [list $cell [get_property IDELAY_VALUE $cell] [get_property LOC $cell]]}
set receipt [open [file join $out scope.txt] w]
puts $receipt "Input checkpoint: $dcp"
puts $receipt {Scope: fixed routed candidate; declared input-window STA and historical-window counterfactual.}
puts $receipt {No device access, physical eye measurement, DCP save or hardware export.}
puts $receipt "Data IDELAY settings: $fixed; clock IDELAY count: 0"
close $receipt
write_xdc -type timing -force [file join $out declared_effective_timing.xdc]
report_clocks -file [file join $out clocks.rpt]
report_route_status -file [file join $out route_status.rpt]
report_bus_skew -file [file join $out bus_skew.rpt]
set summary [open [file join $out sampling_summary.tsv] w]
puts $summary "model\tmin_input_ns\tmax_input_ns\tqueries\tpaths\tsetup_ns\thold_ns\tqualification"
foreach model {declared_25_75 historical_15_85} {
    if {$model eq {declared_25_75}} {set lower 0.892; set upper 2.679} else {set lower 0.535; set upper 3.036}
    # Overwrite both rising-edge bounds, then add both falling-edge bounds.
    foreach type {min max} {
        set value [expr {$type eq {min} ? $lower : $upper}]
        set_input_delay -clock mipi_hs_clk -$type $value $ports
        set_input_delay -clock mipi_hs_clk -clock_fall -add_delay -$type $value $ports
    }
    update_timing
    set rows [open [file join $out ${model}_paths.tsv] w]
    puts $rows "lane\tpolarity\tcorner\tdata_transition\tdelay_type\tpath_count\tworst_slack_ns"
    set setup Inf; set hold Inf; set queries 0; set count 0
    foreach endpoint $endpoints {
        if {![regexp {DataLaneGen\[([01])\]} $endpoint unused lane]} {error {Unknown lane}}
        foreach polarity {p n} {
            set port [get_ports -regexp [format {^dphy_data_hs_%s\[%d\]$} $polarity $lane]]
            foreach corner {Fast Slow} {
                foreach transition {rise fall} {
                    foreach type {max min} {
                        set paths [get_timing_paths -from $port -${transition}_to $endpoint -corner $corner -delay_type $type -max_paths 8 -nworst 8]
                        if {![llength $paths]} {error {Missing sampling paths}}
                        set slacks {}
                        foreach path $paths {lappend slacks [get_property SLACK $path]}
                        set worst [lindex [lsort -real $slacks] 0]
                        if {$type eq {max}} {set setup [expr {min($setup,$worst)}]} else {set hold [expr {min($hold,$worst)}]}
                        puts $rows "$lane\t$polarity\t$corner\t$transition\t$type\t[llength $paths]\t$worst"
                        report_timing -from $port -${transition}_to $endpoint -corner $corner -delay_type $type -max_paths 8 -nworst 8 -path_type full_clock_expanded -significant_digits 3 -append -file [file join $out ${model}_paths.rpt]
                        incr queries; incr count [llength $paths]
                    }
                }
            }
        }
    }
    close $rows
    if {$queries != 32} {error {Incomplete query coverage}}
    set qualification [expr {$setup >= 0 && $hold >= 0 ? {PASS_UNDER_DECLARED_MODEL} : {FAIL}}]
    puts $summary "$model\t$lower\t$upper\t$queries\t$count\t$setup\t$hold\t$qualification"
    flush $summary
    report_timing_summary -delay_type min_max -report_unconstrained -file [file join $out ${model}_timing.rpt]
}
close $summary
set after {}
foreach cell $data {lappend after [list $cell [get_property IDELAY_VALUE $cell] [get_property LOC $cell]]}
if {$fixed ne $after} {error {Unexpected data IDELAY/location changes}}
close_design
puts {SAMPLING_WINDOW_ANALYZED: both models retained; no physical qualification or export}
