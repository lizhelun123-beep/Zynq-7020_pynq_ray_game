# 自定义 RTL → PYNQ Overlay

本分支是 Zynq-7000 上的 AXI-Lite 标量加法器，用于验证完整工程路径，不声称计算加速。保留 Linux/PYNQ 镜像；无 DMA、裸机 PS 初始化、内核重建或板卡自动下载。HLS 使用[独立路径](walkthrough.md)。

## 输入与入口

核准实际 `part`、Vivado release、板卡 DDR/MIO 预设及请求 FCLK。PS 预设文件由调用者提供，脚本使用已有 `ps` BD cell；不能照搬 PYNQ-Z1/Z2 或其他板卡的 DDR 参数。示例 profile 字段如下，数值必须由实际证据确定：

```json
{"board_label":"AX7Z020B","part":"xc7z020clg400-2","tool_version":"2023.1","clock_mhz":100,"ps_preset_tcl":"/absolute/path/to/trusted_ps7_preset.tcl"}
```

从本技能目录运行，使用新的短 ASCII 输出路径以及已经验证的本机 Vivado 启动入口：

```text
python -B scripts/prepare.py profile.json --output /workspace/output/rtl1 --flow rtl
python -B scripts/run_rtl.py /workspace/output/rtl1 --vivado /path/to/vivado --stage sim
python -B scripts/run_rtl.py /workspace/output/rtl1 --vivado /path/to/vivado --stage prepare
```

`prepare.py` 只准备文件，校验输入并冻结原始/暂存模板、PS 预设、配置和阶段脚本的哈希。它仅暂存本技能的小型模板，不能复制用户工程。`run_rtl.py` 在 host Python 中核对输入，再启动 Vivado，避免 Vivado 的 PYTHONHOME 污染 host Python。Windows 可传已验证的 `.cmd` 启动入口，Linux 可传原生可执行入口；每次记录该入口文件哈希。既有输出、重复阶段调用或输入漂移会拒绝；失败日志与阶段 receipt 保留，不自动换目录重试。

阶段通过要求原生退出码 0 和专用完成凭据；仿真还要求实际 `simulate.log` 中的断言计数、零失败及完成标记。Windows XSim 可能关闭继承的 stdout，完成判断不依赖仿真结束后的控制台 `puts`，也不忽略原生错误码。

[project.tcl](../assets/rtl-demo/vivado/project.tcl) 在被 source 时固定源码路径，因此后续从其他目录调用 `make_project` 不会把调用者目录当成 HDL 目录。AXI 的 DATA_WIDTH、ADDR_WIDTH、PROTOCOL 用 `ipx::add_bus_parameter`/`get_bus_parameters` 设置；它们不是 `bus_interface` 属性。封装复用自动推断的地址块，避免再建一个重叠块；只读的中断宽度/复位极性由连线传播并检查结果。IP catalog 查询在创建 project 后执行并使用 `get_ipdefs -all`。

原生准备阶段实际完成封装、IP catalog、PS7/AXI/中断/复位连线、地址分配、BD 验证及 wrapper/输出产品生成，并断言目标 top、地址和关键连接。此阶段不综合。固定 PL 地址为 add32_0=0x43c00000/4 KiB、axi_intc=0x41800000/64 KiB；实际 Linux 镜像是否允许使用该资源需要板端另行核准。

## 分阶段构建与导出

只有实际仿真和准备通过，且本轮获授权，才分别执行：

```text
python -B scripts/run_rtl.py /workspace/output/rtl1 --vivado /path/to/vivado --stage synth
python -B scripts/run_rtl.py /workspace/output/rtl1 --vivado /path/to/vivado --stage impl
```

实现只运行至 route_design，不自动生成比特流。每个阶段只允许这个新 build 中的一次调用；IP 输出产品可能启动自身 OOC runs，应分别记账，不能把它们计成“完全未综合”。

[gate.py](../scripts/gate.py) 的 RTL 模式只解析已核准的 Vivado 2023.1 报告格式，检查 WNS/TNS/WHS/THS、时序覆盖、CDC、DRC 和资源预算；缺失/未知格式拒绝。默认 LUT/FF/BRAM/DSP <70%、Slice <75%，不放宽约束换通过。CDC Warning 也阻止自动放行。实现生成的 `gate.json` 仍要求人工核准时钟/复位拓扑，在保留原始 parsed 字段和报告哈希后填写 `clock_reset_reviewed=true` 与实际 `reviewed_by`；其他门槛必须先为 PASS。不能只改 status 或删除违例。

核对单一 FCLK、同步复位、所有 AXI 时钟/复位、IRQ→AXI INTC→PS 路由及实际报告后，才验证 gate 并显式导出：

```text
python -B scripts/gate.py --receipt /workspace/output/rtl1/inputs.json --record /workspace/output/rtl1/gate.json --verify
python -B scripts/run_rtl.py /workspace/output/rtl1 --vivado /path/to/vivado --stage export
```

导出后比较 XSA 内 BIT 与该 implemented design 的 BIT，提取唯一 HWH，校验 VLNV、完整寄存器表、位宽/访问类型和地址窗；寄存器属性读取实际 HWH 的 PROPERTY 子节点，重复项拒绝。`export/manifest.json` 绑定 BIT/HWH/XSA、输入 receipt 与 gate 身份。XML 解析不导入 PYNQ，不加载硬件。[artifacts.py](../assets/rtl-demo/python/pynq_rtl_demo/artifacts.py) 只证明离线身份与元数据，不证明板上镜像、时钟、Linux 所有权或实际 IRQ。

## Python 和后续板测

仅 host 逻辑使用 `assets/rtl-demo/python` 下的 `Session`。目标板获授权后，才导入 `pynq_rtl_demo.board.open_board(bundle_directory)`；它按 VLNV 绑定 DefaultIP，复用同一 Notebook owner，未确认的下载失败会阻止自动重试。调用 `ip.add(a,b)` 或 `await ip.add_async(a,b)`，结束前使用 `ip.session.close()`；关闭 Session 不代表卸载 Overlay 或释放 Linux 全局资源。

PYNQ 镜像兼容性、资源独占、实际 FCLK 读回、轮询/真实 IRQ、异常取消和冷启动均属单独板测门槛。本示例没有板测结果，不能写“PYNQ 实板全流程通过”。

## 验证范围

2026-11-02 使用实际 Vivado 2023.1、xc7z020clg400-2、请求 FCLK=100 MHz 和已核准的 AX7Z020B PS7 预设完成：原生准备 PASS、RTL 仿真 121 项断言/零失败、顶层综合及 6 个必要 IP OOC 综合 PASS。RTL 分支另有 9 项离线测试通过。仓库原始证据位于 `output/rtlv5/`，本轮索引为 `output/build/skill_rtl_completion_20261102_1/review.json`。

本轮中断时实现、时序/CDC/DRC 闭合、BIT/HWH/XSA 导出和板测均未运行；不能把模板标记为完整硬件构建通过。先前准备失败和仿真入口失败记录保留，最终通过不覆盖这些记录。离线单测不能替代实际工具验证。HLS 分支保留其原有验证范围，本分支通过不转签 HLS。

以上是 add32 模板本体的记录。另有控制与 AXI-Stream/DMA 候选完成实际实现/导出，见[跨题对照及范围](../../references/validation-results.md#package-scope)，不能转签本体。当前包内报告解析器仍存在 CDC 全安全短格式的兼容缺口，见[报告踩坑](../../references/pitfalls.md#p06-reports)；遇到该格式应保留原报告并停止自动放行。

官方接口参考：[AMD AXI bus parameter 示例](https://docs.amd.com/r/2024.1-English/Vitis-Tutorials-Hardware-Acceleration/4-Associate-AXI-Master-Port-to-Pointer-Argument-and-Set-Data-Width)。版本兼容性以本分支实际 2023.1 工具运行记录为准。
