`timescale 1ns/1ps
module add32_tb;
 reg clk=0;always #5 clk=~clk;
 reg resetn=0;reg [11:0] awaddr=0,araddr=0;reg [31:0] wdata=0;
 reg [3:0] wstrb=0;reg awvalid=0,wvalid=0,bready=0,arvalid=0,rready=0;
 wire awready,wready,bvalid,arready,rvalid,interrupt;
 wire [1:0] bresp,rresp;wire [31:0] rdata;
 integer checks=0,failures=0,operations=0;
 reg [31:0] value,control;
 add32 dut(.s_axi_aclk(clk),.s_axi_aresetn(resetn),
 .s_axi_awaddr(awaddr),.s_axi_awprot(3'b0),.s_axi_awvalid(awvalid),.s_axi_awready(awready),
 .s_axi_wdata(wdata),.s_axi_wstrb(wstrb),.s_axi_wvalid(wvalid),.s_axi_wready(wready),
 .s_axi_bresp(bresp),.s_axi_bvalid(bvalid),.s_axi_bready(bready),
 .s_axi_araddr(araddr),.s_axi_arprot(3'b0),.s_axi_arvalid(arvalid),.s_axi_arready(arready),
 .s_axi_rdata(rdata),.s_axi_rresp(rresp),.s_axi_rvalid(rvalid),.s_axi_rready(rready),.interrupt(interrupt));
 task ck(input logic ok,input string name);
  begin checks++;if(ok!==1'b1)begin failures++;$display("RTL_DEMO_FAIL %s time=%0t",name,$time);end end
 endtask
 task wr(input [11:0]addr,input [31:0]data,input [3:0]strb,input integer ad,wd,stall,input [1:0]expected);
  reg [1:0]saved;
  begin
   fork
    begin repeat(ad)@(negedge clk);@(negedge clk);awaddr=addr;awvalid=1;@(posedge clk);while(!awready)@(posedge clk);@(negedge clk);awvalid=0;end
    begin repeat(wd)@(negedge clk);@(negedge clk);wdata=data;wstrb=strb;wvalid=1;@(posedge clk);while(!wready)@(posedge clk);@(negedge clk);wvalid=0;end
   join
   wait(bvalid===1'b1);@(negedge clk);saved=bresp;
   repeat(stall)begin @(negedge clk);ck(bvalid&&bresp===saved,"BVALID/BRESP held under backpressure");end
   ck(bresp===expected,"write response");bready=1;@(posedge clk);@(negedge clk);bready=0;
  end
 endtask
 task rd(input [11:0]addr,input integer stall,input [1:0]expected,output [31:0]data);
  reg [31:0]saved;reg[1:0]saved_resp;
  begin
   @(negedge clk);araddr=addr;arvalid=1;@(posedge clk);while(!arready)@(posedge clk);@(negedge clk);arvalid=0;
   wait(rvalid===1'b1);@(negedge clk);saved=rdata;saved_resp=rresp;
   repeat(stall)begin @(negedge clk);ck(rvalid&&rdata===saved&&rresp===saved_resp,"RVALID/RDATA/RRESP held under backpressure");end
   ck(rresp===expected,"read response");data=rdata;rready=1;@(posedge clk);@(negedge clk);rready=0;
  end
 endtask
 task wait_done;
  integer n;
  begin control=2;n=0;while(control[1]&&n<10)begin rd(0,0,0,control);n++;end ck(!control[1]&&control[2],"bounded completion and DONE");end
 endtask
 task vector(input [31:0]a,b,expected);
  begin
   wr('h10,a,15,0,3,1,0);wr('h14,b,15,3,0,1,0);wr(0,1,1,0,0,0,0);
   wait_done();rd('h18,1,0,value);ck(value===expected,"modulo uint32 sum");
   operations++;rd('h1c,0,0,value);ck(value===operations,"exactly one COUNT increment");
  end
 endtask
 initial begin #100000;$display("RTL_DEMO_TIMEOUT");$fatal(1,"testbench deadline");end
 initial begin
  repeat(4)@(negedge clk);resetn=1;
  rd('h0c,3,0,value);ck(value===32'h10000,"VERSION");
  wr('h10,32'h12345678,15,0,4,3,0);wr('h10,32'h0000ab00,2,4,0,2,0);
  rd('h10,2,0,value);ck(value===32'h1234ab78,"WSTRB updates only selected byte");
  wr('h10,32'hffffffff,0,0,0,0,0);rd('h10,0,0,value);ck(value===32'h1234ab78,"zero WSTRB");
  wr('h18,12,15,0,0,0,2);wr('hffc,12,15,0,0,0,2);wr('h011,12,15,0,0,0,2);
  rd('hffc,0,2,value);ck(value===0,"unknown read");rd('h011,0,2,value);ck(value===0,"unaligned read");
  vector(0,0,0);vector(32'hffffffff,1,0);vector(32'h80000000,32'h80000000,0);vector(1234,4321,5555);
  wr('h10,7,15,0,0,0,0);wr('h14,6,15,0,0,0,0);wr(0,1,1,0,0,0,0);
  wr('h10,300,15,0,0,0,0);wait_done();rd('h18,0,0,value);ck(value===13,"START captures operands");operations++;
  wr('h08,1,1,0,0,0,0);wr(0,1,1,0,0,0,0);wr(0,1,1,0,0,0,2);wait_done();
  rd('h04,0,0,value);ck(value===1&&interrupt,"level IRQ and pending");
  wr('h08,0,1,0,0,0,0);ck(!interrupt,"mask");rd('h04,0,0,value);ck(value===1,"mask preserves pending");
  wr('h08,1,1,0,0,0,0);ck(interrupt,"reenable");wr('h04,0,1,0,0,0,0);ck(interrupt,"W1C zero");
  wr('h04,1,1,0,0,0,0);ck(!interrupt,"W1C one");rd(0,0,0,value);ck(!value[2],"DONE follows STATUS");
  wr(0,1,1,0,0,0,0);@(negedge clk);resetn=0;repeat(3)@(negedge clk);
  ck(!bvalid&&!rvalid&&!interrupt,"reset response/IRQ outputs");resetn=1;repeat(12)@(negedge clk);
  rd(0,0,0,value);ck(value===0,"reset cancels operation");rd('h1c,0,0,value);ck(value===0,"reset COUNT");
  rd('h10,0,0,value);ck(value===0,"reset operands");rd('h0c,0,0,value);ck(value===32'h10000,"reset VERSION");
  $display("RTL_DEMO_RESULT checks=%0d failures=%0d",checks,failures);
  if(failures)$fatal(1,"RTL contract failure");
  $display("RTL_DEMO_PASS");$finish;
 end
endmodule
