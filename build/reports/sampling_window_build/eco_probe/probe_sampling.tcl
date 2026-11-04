# Exploratory ECO STA. Input DCP is never overwritten; no hardware export.
if {$argc != 2} {error {Usage: probe_sampling.tcl routed.dcp fresh_output}}
set dcp [file normalize [lindex $argv 0]]
set out [file normalize [lindex $argv 1]]
if {[file exists $out]} {error {Preserve prior output}}
file mkdir $out
open_checkpoint $dcp
set ports [get_ports {dphy_data_hs_p[*] dphy_data_hs_n[*]}]
set ends [get_pins -hier -filter {REF_PIN_NAME == DDLY && NAME =~ *HSDeserializerX/Deserializer/DDLY}]
set data [get_cells -hier -filter {REF_NAME == IDELAYE2 && NAME =~ *HSDeserializerX/*InputDelay}]
set clock [get_cells -hier -filter {REF_NAME == IDELAYE2 && NAME =~ *ClockLane/HSClockingX/*InputDelay}]
if {[llength $data] != 2 || [llength $clock] != 1 || [llength $ends] != 2} {error {Unexpected netlist}}
set f [open [file join $out sampling_probe.tsv] w]
puts $f "topology\tdata_taps\tcorner\tsetup_ns\thold_ns"
proc sample {topology taps} {
    global data ports ends f out
    set_property IDELAY_VALUE $taps $data
    update_timing
    foreach corner {Fast Slow} {
        set values {}
        foreach type {max min} {
            set paths [get_timing_paths -from $ports -to $ends -corner $corner -delay_type $type -max_paths 8 -nworst 8]
            if {![llength $paths]} {error {Missing sampled paths}}
            set slacks {}
            foreach p $paths {lappend slacks [get_property SLACK $p]}
            lappend values [lindex [lsort -real $slacks] 0]
        }
        puts $f "$topology\t$taps\t$corner\t[join $values \t]"
        flush $f
    }
}
sample baseline 12
foreach taps {18 24 31} {sample original_clock $taps}
set_property IDELAY_VALUE 12 $data
set innet [get_nets -of_objects [get_pins $clock/IDATAIN]]
set outnet [get_nets -of_objects [get_pins $clock/DATAOUT]]
set loads [get_pins -leaf -of_objects $outnet -filter {DIRECTION == IN}]
set receipt [open [file join $out eco_scope.txt] w]
puts $receipt "Exploratory clock-zero-tap bypass; external camera constraints unchanged."
puts $receipt "Input checkpoint: $dcp"
puts $receipt "Clock cell: $clock; inputs: $innet; outputs: $outnet; loads: $loads"
close $receipt
route_design -unroute -nets [concat $innet $outnet]
disconnect_net -net $innet -objects [get_pins $clock/IDATAIN]
disconnect_net -net $outnet -objects $loads
remove_cell $clock
connect_net -net $innet -objects $loads
remove_net $outnet
route_design -nets $innet
foreach taps {12 15 18 21} {sample bypass_zero_clock $taps}
close $f
report_route_status -file [file join $out eco_route_status.rpt]
report_timing_summary -delay_type min_max -report_unconstrained -file [file join $out eco_last_timing.rpt]
close_design
puts {SAMPLING_PROBE_COMPLETE; exploratory only, no export}
