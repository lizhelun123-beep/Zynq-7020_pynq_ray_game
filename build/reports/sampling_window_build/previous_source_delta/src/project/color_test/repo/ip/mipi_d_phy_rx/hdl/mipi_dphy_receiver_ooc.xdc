# Generated from build/run_pl.py camera_timing_ooc_xdc.
# IP-only OOC design: same final nominal camera model as top-level system.xdc.
# 12MHz XVCLK / HS140MHz; inherited 15%/85% UI envelope, not physical signoff.
create_clock -name dphy_clk_hs_p -period 7.143 -waveform {0 3.571} [get_ports dphy_clk_hs_p]
set_input_delay -clock dphy_clk_hs_p -min 0.535 [get_ports {dphy_data_hs_p[*] dphy_data_hs_n[*]}]
set_input_delay -clock dphy_clk_hs_p -max 3.036 [get_ports {dphy_data_hs_p[*] dphy_data_hs_n[*]}]
set_input_delay -clock dphy_clk_hs_p -clock_fall -add_delay -min 0.535 [get_ports {dphy_data_hs_p[*] dphy_data_hs_n[*]}]
set_input_delay -clock dphy_clk_hs_p -clock_fall -add_delay -max 3.036 [get_ports {dphy_data_hs_p[*] dphy_data_hs_n[*]}]
