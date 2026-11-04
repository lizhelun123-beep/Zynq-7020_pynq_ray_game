# Generated from build/run_pl.py camera_timing_xdc; final executed hardware.json tables.
# XVCLK nominal 12 MHz; HS nominal 140 MHz; lane 280 Mb/s; byte 35 MHz.
# Sensor 3034=1a,3035=21,3036=46,3037=05,3108=11,4837=24.
# Evidence: build/timing_evidence/. No new physical frequency/eye measurement.
# USER_DECLARED_UNMEASURED pin window; see build/camera_input_contract.json.
# Passing STA is conditional on this envelope, not physical pin signoff.
# This top-level file is the sole owner of the MIPI clock and input delays.
set_property BITSTREAM.GENERAL.COMPRESS TRUE [current_design]
create_clock -name mipi_hs_clk -period 7.143000000 -waveform {0 3.571000000} [get_ports dphy_hs_clock_clk_p]
set_input_delay -clock mipi_hs_clk -min 0.892000 [get_ports {dphy_data_hs_p[*] dphy_data_hs_n[*]}]
set_input_delay -clock mipi_hs_clk -max 2.679000 [get_ports {dphy_data_hs_p[*] dphy_data_hs_n[*]}]
set_input_delay -clock mipi_hs_clk -clock_fall -add_delay -min 0.892000 [get_ports {dphy_data_hs_p[*] dphy_data_hs_n[*]}]
set_input_delay -clock mipi_hs_clk -clock_fall -add_delay -max 2.679000 [get_ports {dphy_data_hs_p[*] dphy_data_hs_n[*]}]
