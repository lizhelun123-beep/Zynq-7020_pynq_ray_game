if {![info exists ::env(PYNQ_DEMO_CONFIG)]} {error "Set PYNQ_DEMO_CONFIG to prepared config.tcl"}
source [file normalize $::env(PYNQ_DEMO_CONFIG)]
exec $DEMO_PYTHON -B $DEMO_VERIFY --receipt [file join $DEMO_BUILD inputs.json]
if {![info exists ::env(PYNQ_DEMO_STAGE)]} {error "Set an explicit PYNQ_DEMO_STAGE"}
set stage $::env(PYNQ_DEMO_STAGE)
proc mark_stage {name} {
    global DEMO_BUILD
    set out [open [file join $DEMO_BUILD $name.pass] w]
    puts $out "Tool stage returned successfully;scope limited to this stage."
    close $out
}
proc require_stage {name} {
    global DEMO_BUILD
    if {![file isfile [file join $DEMO_BUILD $name.pass]]} {error "Missing prerequisite $name"}
}
