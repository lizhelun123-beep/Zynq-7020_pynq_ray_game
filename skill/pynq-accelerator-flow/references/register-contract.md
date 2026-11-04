# 先区分寄存器 ABI

IP-XACT 描述、实际 HDL、HWH 和驱动须一致；接口名称或地址相似不能证明语义相同。

| 项目 | HLS scalar-demo | 自定义 RTL add32 |
|---|---|---|
| VLNV | `example.org:hls:add_bias:1.0` | `pynq.local:rtl:add32:1.0` |
| CTRL 0x00 | HLS `ap_ctrl_hs`，按生成头文件解释 | bit0 START W1P、bit1 BUSY、bit2 DONE |
| 0x04 / 0x08 | GIE / IER | STATUS W1C / IRQ_ENABLE |
| 0x0c | ISR TOW | VERSION 只读，0x00010000 |
| 参数与结果 | x=0x10、bias=0x18、y=0x20 | A=0x10、B=0x14、RESULT=0x18、COUNT=0x1c |
| 运算 | 以实际 HLS 定义为准 | uint32 相加，按 2^32 回绕 |

HLS 的 TOW 只能写回已观察到的待处理中断位；直接向未置位的位写 1 会翻转状态。自定义 RTL 的 STATUS 是 W1C，不能套用 TOW 推理。add32 的 DONE 镜像 STATUS，驱动必须先读结果/完成状态，再清除 STATUS。

## 自定义 RTL 的行为约定

- AW 和 W 可以不同拍到达，分别缓存；B/R 响应在背压下保持稳定。A/B 写入遵守 WSTRB。未对齐、未映射及只读寄存器写入返回 SLVERR。
- START 只接受空闲状态并捕获 A/B；计算期间修改参数只影响下次任务。重叠 START 返回 SLVERR；START 清旧 pending，完成在第八个后续时钟置 pending 并更新 RESULT/COUNT。
- IRQ 是 `pending && enable` 的高电平。屏蔽不清 pending；STATUS bit0 写 1 清除，写 0 不变；同拍完成优先于清除。同步低有效复位清运行状态、结果和中断。
- Python 参数必须在首次 MMIO 前完成检查。使用单调时钟设置超时；超时/取消进入 unknown，不立即释放、重试或声称硬件停机。
- `recover_if_idle()` 只检查这个无内存主端口的标量 IP；不证明 DMA 停机。取消 IRQ 等待后保守废弃该 Session 的 IRQ 路径，确认空闲后可继续轮询；重新启用 IRQ 需要重新建立明确的独占所有权。

驱动代码：[core.py](../assets/rtl-demo/python/pynq_rtl_demo/core.py)。原始 RTL 和公开仿真分别位于 [add32.v](../assets/rtl-demo/hdl/add32.v)、[add32_tb.sv](../assets/rtl-demo/sim/add32_tb.sv)。这些是这个示例的 ABI，不能作为其他 IP 的默认寄存器表。

参考：[AMD IP 寄存器定义](https://docs.amd.com/r/2023.1-English/Vitis-Tutorials-Hardware-Acceleration/Step-3-Set-the-Definition-of-AXI-Control-Slave-Registers-Including-CTRL-and-User-Kernel-Arguments)。HLS 中断细节见[原有参考](interrupts.md)。
