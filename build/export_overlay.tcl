# Continue from the exact routed checkpoint used for the parent reports.
# No synthesis, implementation, timing-model edits or device access.
if {$argc != 2} {error {Usage: export_overlay.tcl routed.dcp fresh_output}}
if {![string match {2023.1*} [version -short]]} {error {Vivado 2023.1 required}}
set checkpoint [file normalize [lindex $argv 0]]
set out [file normalize [lindex $argv 1]]
if {[file exists $out]} {error {Preserve existing export output}}
file mkdir $out
set stage open_checkpoint
set result [catch {
    open_checkpoint $checkpoint
    set reports [file join $out reports]
    set artifacts [file join $out artifacts]
    file mkdir $reports $artifacts
    set stage timing_gate
    report_timing_summary -delay_type min_max -report_unconstrained -file [file join $reports export_timing.rpt]
    report_route_status -file [file join $reports export_route_status.rpt]
    report_bus_skew -file [file join $reports export_bus_skew.rpt]
    set stream [open [file join $reports export_timing.rpt] r]
    set timing_text [read $stream]
    close $stream
    if {[string first {All user specified timing constraints are met.} $timing_text] < 0} {error {Checkpoint timing does not pass}}
    foreach delay {max min} {
        set paths [get_timing_paths -delay_type $delay -max_paths 1]
        if {[llength $paths] != 1 || [get_property SLACK [lindex $paths 0]] < 0} {error {Checkpoint has negative/missing timing path}}
    }
    set stage bitstream
    cd $artifacts
    write_bitstream -force system_wrapper.bit
    set stage platform_export
    write_hw_platform -fixed -include_bit -force [file join $artifacts system_wrapper.xsa]
    close_project
    set stage complete
} message details]
set stream [open [file join $out status.tsv] w]
puts $stream "stage\tresult"
puts $stream "$stage\t[expr {$result ? {FAILED} : {EXPORTED_FROM_ROUTED_CHECKPOINT}}]"
close $stream
if {$result} {return -options $details $message}
puts {OVERLAY_EXPORTED: exact routed checkpoint; conditional pin-window STA; not board-qualified}
