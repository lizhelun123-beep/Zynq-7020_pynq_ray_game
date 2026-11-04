# Capture at SOURCE time;make_project may later run from a different caller/CWD.
set ::pynq_add32_source [file normalize [file join [file dirname [info script]] ..]]

proc pynq_add32_parameter {interface name value} {
    set parameter [ipx::get_bus_parameters -quiet $name -of_objects $interface]
    if {![llength $parameter]} {set parameter [ipx::add_bus_parameter $name $interface]}
    set_property value $value $parameter
}

proc pynq_add32_interface {core name bus abstraction mode} {
    set interface [ipx::get_bus_interfaces -quiet $name -of_objects $core]
    if {![llength $interface]} {set interface [ipx::add_bus_interface $name $core]}
    set_property interface_mode $mode $interface
    set_property bus_type_vlnv $bus $interface
    set_property abstraction_type_vlnv $abstraction $interface
    return $interface
}

proc pynq_add32_port {interface logical physical} {
    set mapping [ipx::get_port_maps -quiet $logical -of_objects $interface]
    if {![llength $mapping]} {set mapping [ipx::add_port_map $logical $interface]}
    set_property physical_name $physical $mapping
}

proc make_project {build_dir ps_preset part clock_mhz} {
    set source_root $::pynq_add32_source
    set build_dir [file normalize $build_dir]
    if {[file exists $build_dir]} {error "Use a NEW build directory"}
    if {![file isfile $ps_preset]} {error "Trusted PS7 preset missing"}
    file mkdir $build_dir
    create_project add32_pack [file join $build_dir ip_pack] -part $part
    add_files -norecurse [file join $source_root hdl add32.v]
    set_property top add32 [current_fileset]
    update_compile_order -fileset sources_1
    ipx::package_project -root_dir [file join $build_dir ip_repo add32] -vendor pynq.local -library rtl -taxonomy /UserIP -import_files
    set core [ipx::current_core]
    set_property name add32 $core
    set_property version 1.0 $core
    set_property core_revision 1 $core
    set_property display_name {PYNQ RTL Add32} $core
    set bus [pynq_add32_interface $core s_axi xilinx.com:interface:aximm:1.0 xilinx.com:interface:aximm_rtl:1.0 slave]
    # Width/protocol are BUS PARAMETERS,not properties on bus_interface.
    foreach {name value} {PROTOCOL AXI4LITE ADDR_WIDTH 12 DATA_WIDTH 32} {pynq_add32_parameter $bus $name $value}
    foreach {logical physical} {
        AWADDR s_axi_awaddr AWPROT s_axi_awprot AWVALID s_axi_awvalid AWREADY s_axi_awready
        WDATA s_axi_wdata WSTRB s_axi_wstrb WVALID s_axi_wvalid WREADY s_axi_wready
        BRESP s_axi_bresp BVALID s_axi_bvalid BREADY s_axi_bready
        ARADDR s_axi_araddr ARPROT s_axi_arprot ARVALID s_axi_arvalid ARREADY s_axi_arready
        RDATA s_axi_rdata RRESP s_axi_rresp RVALID s_axi_rvalid RREADY s_axi_rready
    } {pynq_add32_port $bus $logical $physical}
    set clock [pynq_add32_interface $core s_axi_aclk xilinx.com:signal:clock:1.0 xilinx.com:signal:clock_rtl:1.0 slave]
    pynq_add32_port $clock CLK s_axi_aclk
    pynq_add32_parameter $clock ASSOCIATED_BUSIF s_axi
    pynq_add32_parameter $clock ASSOCIATED_RESET s_axi_aresetn
    pynq_add32_parameter $clock FREQ_HZ [expr {int($clock_mhz * 1000000)}]
    set reset [pynq_add32_interface $core s_axi_aresetn xilinx.com:signal:reset:1.0 xilinx.com:signal:reset_rtl:1.0 slave]
    pynq_add32_port $reset RST s_axi_aresetn
    pynq_add32_parameter $reset POLARITY ACTIVE_LOW
    set irq [pynq_add32_interface $core interrupt xilinx.com:signal:interrupt:1.0 xilinx.com:signal:interrupt_rtl:1.0 master]
    pynq_add32_port $irq INTERRUPT interrupt
    pynq_add32_parameter $irq SENSITIVITY LEVEL_HIGH
    set map [ipx::get_memory_maps -quiet s_axi -of_objects $core]
    if {![llength $map]} {set map [ipx::add_memory_map s_axi $core]}
    set_property slave_memory_map_ref s_axi $bus
    # package_project infers reg0;reuse it instead of creating overlapping blocks.
    set block [ipx::get_address_blocks -of_objects $map]
    if {[llength $block] > 1} {error "Unexpected multiple inferred address blocks"}
    if {![llength $block]} {set block [ipx::add_address_block Reg $map]}
    set_property name Reg $block
    set_property range 4096 $block
    set_property width 32 $block
    set_property usage register $block
    foreach {name offset access} {CTRL 0 read-write STATUS 4 read-write IRQ_ENABLE 8 read-write VERSION 12 read-only A 16 read-write B 20 read-write RESULT 24 read-only COUNT 28 read-only} {
        set register [ipx::get_registers -quiet $name -of_objects $block]
        if {![llength $register]} {set register [ipx::add_register $name $block]}
        set_property address_offset $offset $register
        set_property size 32 $register
        set_property access $access $register
    }
    ipx::update_checksums $core
    ipx::save_core $core
    ipx::check_integrity -quiet $core
    close_project

    create_project add32 $build_dir -part $part
    set_property target_language Verilog [current_project]
    set_property ip_repo_paths [list [file join $build_dir ip_repo]] [current_project]
    update_ip_catalog
    foreach vlnv {xilinx.com:ip:processing_system7:5.5 xilinx.com:ip:axi_interconnect:2.1 xilinx.com:ip:axi_intc:4.1 xilinx.com:ip:proc_sys_reset:5.0 pynq.local:rtl:add32:1.0} {
        if {![llength [get_ipdefs -all -quiet $vlnv]]} {error "IP unavailable: $vlnv"}
    }
    create_bd_design system
    set ps [create_bd_cell -type ip -vlnv xilinx.com:ip:processing_system7:5.5 ps7]
    source -encoding utf-8 $ps_preset
    set_property -dict [list CONFIG.PCW_USE_M_AXI_GP0 1 CONFIG.PCW_EN_CLK0_PORT 1 CONFIG.PCW_FPGA0_PERIPHERAL_FREQMHZ $clock_mhz CONFIG.PCW_USE_FABRIC_INTERRUPT 1 CONFIG.PCW_IRQ_F2P_INTR 1] $ps
    make_bd_intf_pins_external [get_bd_intf_pins ps7/DDR]
    make_bd_intf_pins_external [get_bd_intf_pins ps7/FIXED_IO]
    create_bd_cell -type ip -vlnv pynq.local:rtl:add32:1.0 add32_0
    create_bd_cell -type ip -vlnv xilinx.com:ip:axi_interconnect:2.1 ctrl
    set_property -dict [list CONFIG.NUM_SI 1 CONFIG.NUM_MI 2] [get_bd_cells ctrl]
    create_bd_cell -type ip -vlnv xilinx.com:ip:axi_intc:4.1 axi_intc
    # C_NUM_INTR_INPUTS is propagation-only;the connected source determines width.
    set_property -dict [list CONFIG.C_KIND_OF_INTR 0 CONFIG.C_IRQ_CONNECTION 1] [get_bd_cells axi_intc]
    create_bd_cell -type ip -vlnv xilinx.com:ip:proc_sys_reset:5.0 rst
    # C_EXT_RESET_HIGH is propagation-only in BD;the reset interface supplies polarity.
    foreach {name value} {one 1 zero 0} {
        create_bd_cell -type ip -vlnv xilinx.com:ip:xlconstant:1.1 $name
        set_property CONFIG.CONST_VAL $value [get_bd_cells $name]
    }
    connect_bd_intf_net [get_bd_intf_pins ps7/M_AXI_GP0] [get_bd_intf_pins ctrl/S00_AXI]
    connect_bd_intf_net [get_bd_intf_pins ctrl/M00_AXI] [get_bd_intf_pins add32_0/s_axi]
    connect_bd_intf_net [get_bd_intf_pins ctrl/M01_AXI] [get_bd_intf_pins axi_intc/s_axi]
    connect_bd_net [get_bd_pins ps7/FCLK_CLK0] [get_bd_pins ps7/M_AXI_GP0_ACLK] [get_bd_pins ctrl/ACLK] [get_bd_pins ctrl/S00_ACLK] [get_bd_pins ctrl/M00_ACLK] [get_bd_pins ctrl/M01_ACLK] [get_bd_pins add32_0/s_axi_aclk] [get_bd_pins axi_intc/s_axi_aclk] [get_bd_pins rst/slowest_sync_clk]
    connect_bd_net [get_bd_pins ps7/FCLK_RESET0_N] [get_bd_pins rst/ext_reset_in]
    connect_bd_net [get_bd_pins one/dout] [get_bd_pins rst/dcm_locked]
    connect_bd_net [get_bd_pins zero/dout] [get_bd_pins rst/aux_reset_in] [get_bd_pins rst/mb_debug_sys_rst]
    connect_bd_net [get_bd_pins rst/interconnect_aresetn] [get_bd_pins ctrl/ARESETN]
    connect_bd_net [get_bd_pins rst/peripheral_aresetn] [get_bd_pins ctrl/S00_ARESETN] [get_bd_pins ctrl/M00_ARESETN] [get_bd_pins ctrl/M01_ARESETN] [get_bd_pins add32_0/s_axi_aresetn] [get_bd_pins axi_intc/s_axi_aresetn]
    connect_bd_net [get_bd_pins add32_0/interrupt] [get_bd_pins axi_intc/intr]
    connect_bd_net [get_bd_pins axi_intc/irq] [get_bd_pins ps7/IRQ_F2P]
    assign_bd_address
    set space [get_bd_addr_spaces ps7/Data]
    foreach {pattern offset range} {*add32_0* 0x43c00000 4K *axi_intc* 0x41800000 64K} {
        set segment [get_bd_addr_segs -of_objects $space -filter "NAME =~ $pattern"]
        if {[llength $segment] != 1} {error "Expected one mapped segment for $pattern"}
        set_property offset $offset $segment
        set_property range $range $segment
    }
    validate_bd_design
    if {[get_property CONFIG.C_NUM_INTR_INPUTS [get_bd_cells axi_intc]] != 1} {error "Expected one propagated interrupt input"}
    if {[get_property CONFIG.C_EXT_RESET_HIGH [get_bd_cells rst]] != 0} {error "Expected propagated active-low external reset"}
    save_bd_design
    generate_target all [get_files */system.bd]
    set wrapper [make_wrapper -files [get_files */system.bd] -top]
    add_files -norecurse $wrapper
    set_property top system_wrapper [current_fileset]
    update_compile_order -fileset sources_1
}
