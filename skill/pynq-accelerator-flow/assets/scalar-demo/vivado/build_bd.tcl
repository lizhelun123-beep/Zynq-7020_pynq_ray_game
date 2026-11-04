source [file join [file dirname [info script]] .. common.tcl]
if {$stage ni {prepare synth impl export}} {error "Vivado stage must be prepare/synth/impl/export"}
if {[version -short] ne $DEMO_TOOL_VERSION} {error "Vivado release differs from prepared profile"}
if {![llength [get_parts -quiet $DEMO_PART]]} {error "Part unavailable"}
set project_dir [file join $DEMO_BUILD vivado]
if {$stage eq "prepare"} {
    require_stage hls_ip
    if {[file exists $project_dir]} {error "Vivado output exists;use a new build"}
    create_project scalar_demo $project_dir -part $DEMO_PART
    set_property ip_repo_paths [list [file join $DEMO_BUILD hls solution impl ip]] [current_project]
    update_ip_catalog
    foreach vlnv {xilinx.com:ip:processing_system7:5.5 xilinx.com:ip:axi_interconnect:2.1 xilinx.com:ip:axi_intc:4.1 example.org:hls:add_bias:1.0} {
        if {![llength [get_ipdefs -all -quiet $vlnv]]} {error "Missing IP $vlnv"}
    }
    create_bd_design design_1
    set ps [create_bd_cell -type ip -vlnv xilinx.com:ip:processing_system7:5.5 ps7]
    # Trusted input must configure THIS cell's DDR/MIO for the actual board.
    source $DEMO_PS_PRESET
    set_property -dict [list CONFIG.PCW_USE_M_AXI_GP0 {1} CONFIG.PCW_EN_CLK0_PORT {1} CONFIG.PCW_FPGA0_PERIPHERAL_FREQMHZ $DEMO_CLOCK_MHZ CONFIG.PCW_USE_FABRIC_INTERRUPT {1} CONFIG.PCW_IRQ_F2P_INTR {1}] $ps
    make_bd_intf_pins_external [get_bd_intf_pins ps7/DDR]
    make_bd_intf_pins_external [get_bd_intf_pins ps7/FIXED_IO]
    create_bd_cell -type ip -vlnv example.org:hls:add_bias:1.0 add_bias_0
    create_bd_cell -type ip -vlnv xilinx.com:ip:axi_interconnect:2.1 ctrl
    set_property -dict [list CONFIG.NUM_SI {1} CONFIG.NUM_MI {2}] [get_bd_cells ctrl]
    create_bd_cell -type ip -vlnv xilinx.com:ip:axi_intc:4.1 axi_intc
    set_property -dict [list CONFIG.C_NUM_INTR_INPUTS {1} CONFIG.C_KIND_OF_INTR {0} CONFIG.C_IRQ_CONNECTION {1}] [get_bd_cells axi_intc]
    create_bd_cell -type ip -vlnv xilinx.com:ip:proc_sys_reset:5.0 rst
    set_property CONFIG.C_EXT_RESET_HIGH {0} [get_bd_cells rst]
    create_bd_cell -type ip -vlnv xilinx.com:ip:xlconstant:1.1 one
    set_property CONFIG.CONST_VAL {1} [get_bd_cells one]
    create_bd_cell -type ip -vlnv xilinx.com:ip:xlconstant:1.1 zero
    set_property CONFIG.CONST_VAL {0} [get_bd_cells zero]
    connect_bd_intf_net [get_bd_intf_pins ps7/M_AXI_GP0] [get_bd_intf_pins ctrl/S00_AXI]
    connect_bd_intf_net [get_bd_intf_pins ctrl/M00_AXI] [get_bd_intf_pins add_bias_0/s_axi_control]
    connect_bd_intf_net [get_bd_intf_pins ctrl/M01_AXI] [get_bd_intf_pins axi_intc/s_axi]
    connect_bd_net [get_bd_pins ps7/FCLK_CLK0] [get_bd_pins ps7/M_AXI_GP0_ACLK] [get_bd_pins ctrl/ACLK] [get_bd_pins ctrl/S00_ACLK] [get_bd_pins ctrl/M00_ACLK] [get_bd_pins ctrl/M01_ACLK] [get_bd_pins add_bias_0/ap_clk] [get_bd_pins axi_intc/s_axi_aclk] [get_bd_pins rst/slowest_sync_clk]
    connect_bd_net [get_bd_pins ps7/FCLK_RESET0_N] [get_bd_pins rst/ext_reset_in]
    connect_bd_net [get_bd_pins one/dout] [get_bd_pins rst/dcm_locked]
    connect_bd_net [get_bd_pins zero/dout] [get_bd_pins rst/aux_reset_in] [get_bd_pins rst/mb_debug_sys_rst]
    connect_bd_net [get_bd_pins rst/interconnect_aresetn] [get_bd_pins ctrl/ARESETN] [get_bd_pins ctrl/S00_ARESETN] [get_bd_pins ctrl/M00_ARESETN] [get_bd_pins ctrl/M01_ARESETN]
    connect_bd_net [get_bd_pins rst/peripheral_aresetn] [get_bd_pins add_bias_0/ap_rst_n] [get_bd_pins axi_intc/s_axi_aresetn]
    connect_bd_net [get_bd_pins add_bias_0/interrupt] [get_bd_pins axi_intc/intr]
    connect_bd_net [get_bd_pins axi_intc/irq] [get_bd_pins ps7/IRQ_F2P]
    assign_bd_address
    validate_bd_design
    save_bd_design
    generate_target all [get_files design_1.bd]
    set wrapper [make_wrapper -files [get_files design_1.bd] -top]
    add_files -norecurse $wrapper
    set_property top design_1_wrapper [current_fileset]
    update_compile_order -fileset sources_1
    mark_stage vivado_prepare
} else {
    require_stage vivado_prepare
    open_project [file join $project_dir scalar_demo.xpr]
    if {$stage eq "synth"} {
        launch_runs synth_1 -jobs 2
        wait_on_run synth_1
        if {[get_property PROGRESS [get_runs synth_1]] ne "100%"} {error "Synthesis incomplete"}
        mark_stage vivado_synth
    } elseif {$stage eq "impl"} {
        require_stage vivado_synth
        launch_runs impl_1 -to_step route_design -jobs 2
        wait_on_run impl_1
        if {[get_property PROGRESS [get_runs impl_1]] ne "100%"} {error "Implementation incomplete"}
        open_run impl_1
        set reports [file join $DEMO_BUILD reports]
        file mkdir $reports
        report_timing_summary -report_unconstrained -file [file join $reports timing.rpt]
        report_cdc -file [file join $reports cdc.rpt]
        report_drc -file [file join $reports drc.rpt]
        report_utilization -file [file join $reports utilization.rpt]
        report_clocks -file [file join $reports clocks.rpt]
        mark_stage vivado_impl
    } else {
        require_stage vivado_impl
        if {![info exists ::env(PYNQ_DEMO_GATE_RECORD)]} {error "Provide reviewed gate record"}
        exec $DEMO_PYTHON -B $DEMO_GATE --verify --receipt [file join $DEMO_BUILD inputs.json] --record $::env(PYNQ_DEMO_GATE_RECORD)
        launch_runs impl_1 -to_step write_bitstream -jobs 2
        wait_on_run impl_1
        if {[get_property PROGRESS [get_runs impl_1]] ne "100%"} {error "Bitstream run incomplete"}
        open_run impl_1
        file mkdir [file join $DEMO_BUILD export]
        write_hw_platform -fixed -include_bit -file [file join $DEMO_BUILD export scalar.xsa]
        mark_stage vivado_export
    }
}
close_project
exit
