`timescale 1ns/1ps
// Example-specific ABI: STATUS(0x04) is W1C;IRQ_ENABLE is 0x08.
module add32(
 input s_axi_aclk,s_axi_aresetn,
 input [11:0] s_axi_awaddr,input [2:0] s_axi_awprot,input s_axi_awvalid,output s_axi_awready,
 input [31:0] s_axi_wdata,input [3:0] s_axi_wstrb,input s_axi_wvalid,output s_axi_wready,
 output reg [1:0] s_axi_bresp,output reg s_axi_bvalid,input s_axi_bready,
 input [11:0] s_axi_araddr,input [2:0] s_axi_arprot,input s_axi_arvalid,output s_axi_arready,
 output reg [31:0] s_axi_rdata,output reg [1:0] s_axi_rresp,output reg s_axi_rvalid,input s_axi_rready,
 output interrupt
);
 reg aw_pending,w_pending;
 reg [11:0] aw_addr;
 reg [31:0] w_data,a,b,result,count,captured_sum;
 reg [3:0] w_strb,remaining;
 reg busy,pending,enabled;
 integer lane;
 assign s_axi_awready=s_axi_aresetn&&!aw_pending&&!s_axi_bvalid;
 assign s_axi_wready=s_axi_aresetn&&!w_pending&&!s_axi_bvalid;
 assign s_axi_arready=s_axi_aresetn&&!s_axi_rvalid;
 assign interrupt=enabled&&pending;
 always @(posedge s_axi_aclk)begin
  if(!s_axi_aresetn)begin
   aw_pending<=0;w_pending<=0;aw_addr<=0;w_data<=0;w_strb<=0;
   s_axi_bvalid<=0;s_axi_bresp<=0;s_axi_rvalid<=0;s_axi_rdata<=0;s_axi_rresp<=0;
   a<=0;b<=0;result<=0;count<=0;captured_sum<=0;
   busy<=0;pending<=0;enabled<=0;remaining<=0;
  end else begin
   if(s_axi_awready&&s_axi_awvalid)begin aw_pending<=1;aw_addr<=s_axi_awaddr;end
   if(s_axi_wready&&s_axi_wvalid)begin w_pending<=1;w_data<=s_axi_wdata;w_strb<=s_axi_wstrb;end
   if(s_axi_bvalid&&s_axi_bready)s_axi_bvalid<=0;
   if(aw_pending&&w_pending&&!s_axi_bvalid)begin
    aw_pending<=0;w_pending<=0;s_axi_bvalid<=1;s_axi_bresp<=0;
    case(aw_addr)
     12'h000:if(w_strb[0]&&w_data[0])begin
       if(busy)s_axi_bresp<=2;
       else begin busy<=1;remaining<=8;pending<=0;captured_sum<=a+b;end
     end
     12'h004:if(w_strb[0]&&w_data[0])pending<=0;
     12'h008:if(w_strb[0])enabled<=w_data[0];
     12'h010:for(lane=0;lane<4;lane=lane+1)if(w_strb[lane])a[8*lane+:8]<=w_data[8*lane+:8];
     12'h014:for(lane=0;lane<4;lane=lane+1)if(w_strb[lane])b[8*lane+:8]<=w_data[8*lane+:8];
     default:s_axi_bresp<=2;
    endcase
   end
   if(s_axi_rvalid&&s_axi_rready)s_axi_rvalid<=0;
   if(s_axi_arready&&s_axi_arvalid)begin
    s_axi_rvalid<=1;s_axi_rresp<=0;
    case(s_axi_araddr)
     12'h000:s_axi_rdata<={29'b0,pending,busy,1'b0};
     12'h004:s_axi_rdata<={31'b0,pending};
     12'h008:s_axi_rdata<={31'b0,enabled};
     12'h00c:s_axi_rdata<=32'h00010000;
     12'h010:s_axi_rdata<=a;
     12'h014:s_axi_rdata<=b;
     12'h018:s_axi_rdata<=result;
     12'h01c:s_axi_rdata<=count;
     default:begin s_axi_rdata<=0;s_axi_rresp<=2;end
    endcase
   end
   // Completion has priority over a simultaneous STATUS W1C.
   if(busy)begin
    if(remaining==1)begin result<=captured_sum;count<=count+1;busy<=0;pending<=1;remaining<=0;end
    else remaining<=remaining-1;
   end
  end
 end
endmodule
