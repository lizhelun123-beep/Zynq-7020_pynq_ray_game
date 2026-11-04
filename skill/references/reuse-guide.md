# 七项技能的复用说明

从技能包根目录执行下列命令。需要已有 Python 3.8+；数组例子另需已有 NumPy，Tcl 文本检查使用 tkinter。使用提示词工作流时，将目标工程、输入文件和验收目标填入对应 SKILL.md 的提示词。

先保留整个技能包的目录结构，再按任务读取一个入口。已有项目先定位规范源码、当前驱动和实际版本。构建或板端操作使用当前任务已有授权；下列离线命令不需要连接板卡。

## pynq-development

- **适用场景**：Linux/PYNQ 应用、Overlay/IP 接入、Python/C 数据接口。
- **最小输入**：实际板卡、镜像/PYNQ/Python 版本；BIT/HWH 来源；目标 IP 名称；数组接口另给 shape、dtype、stride 和 ABI。
- **使用**：先读[开发入口](../pynq-development/SKILL.md)。离线例子：`python -B pynq-development/scripts/inspect_hwh.py pynq-development/examples/synthetic.hwh --ip demo_dma`。
- **预期结果**：输出 `scope=OFFLINE_DECLARATIONS_ONLY`，例子窗口 `span=65536`；实际项目输出目标 IP 的声明、参数、窗口和待核准项。
- **失效条件**：不支持的 HWH 格式、缺少目标 IP 或接口证据时停止推断；文件声明不作为当前硬件已加载的证据。`register_map` 的完整教程和通用代码生成器尚未提供。
- **验证与经验**：HWH/数组已有离线正反例；真实 C ABI、板端驱动另验。见[验证范围](validation-results.md#package-scope)、[P01](pitfalls.md#p01-overlay)、[P02](pitfalls.md#p02-registers)。

## pynq-accelerator-flow

- **适用场景**：从 HLS 或自定义 RTL 新建 Zynq-7000 标量 Overlay。
- **最小输入**：真实 part、准确工具 release、FCLK 请求、可信同板 PS7 预设；自定义 IP 还需 VLNV、寄存器和中断契约。
- **使用**：从[加速器入口](../pynq-accelerator-flow/SKILL.md)选择 HLS/RTL 路径。离线语法检查：`python -B pynq-accelerator-flow/scripts/validate_template.py`。
- **预期结果**：语法检查输出 `scope=HOST_SOURCE_SYNTAX_ONLY`；实际构建按准备、仿真、综合、实现、导出分别给证据。RTL 完整命令见[RTL 路径](../pynq-accelerator-flow/references/rtl-flow.md)，各阶段只运行获授权部分。
- **失效条件**：PS7 流程不能直接套 MPSoC/Versal；新题须替换示例运算、接口、VLNV、窗口和驱动。输入漂移、未知报告格式或实现门未过时停止导出。当前包内 gate 的 CDC 安全短格式限制见[P06](pitfalls.md#p06-reports)。
- **验证与经验**：包内 add32 模板已有真实准备/仿真/综合记录；跨题候选工程有独立结果，见[范围表](validation-results.md#package-scope)。新板核对见[板卡迁移](../pynq-accelerator-flow/references/board-porting.md)、[P03](pitfalls.md#p03-packaging)。

## pynq-dma-contract

- **适用场景**：AXI DMA/VDMA 的布局、缓存同步、缓冲交接、异常和退出。
- **最小输入**：DMA 类型、格式、有效行字节、stride/span、地址/对齐、分配器及实际完成/停机 API。
- **使用**：读[DMA 入口](../pynq-dma-contract/SKILL.md)；运行 `python -B pynq-dma-contract/scripts/check_layout.py pynq-dma-contract/examples/layout.json`。生命周期例子：`python -B pynq-dma-contract/examples/lifecycle.py`。
- **预期结果**：布局样例为 `PASS_STATIC_DESCRIPTION`、`buffers=3`；生命周期为 `MOCK_LIFECYCLE_ONLY`，确认替身停机后 `owner=released`。实际项目应给出每槽所有权变化和失败处理。
- **失效条件**：地址别名/SG 未建模、分配器或同步未知、停机无法证明设备不再访问缓冲时保留所有权；替身接口不能直接绑定可能阻塞的 PYNQ `wait/stop`。
- **验证与经验**：布局与生命周期已有离线正反例；跨题 DMA 候选硬件完成构建，真实搬运/cache/停机未上板。恢复条件分歧见[P04](pitfalls.md#p04-dma)。

## stream-perf-analysis

- **适用场景**：分析已有视频、音频、传感或推理日志的耗时、吞吐和新鲜度。
- **最小输入**：完整日志、阶段配置、单位、时钟域、启动/连接边界；不直接将任意 UART 日志当累计快照。
- **使用**：读[性能入口](../stream-perf-analysis/SKILL.md)；运行 `python -B stream-perf-analysis/scripts/analyze.py stream-perf-analysis/examples/audio-performance.jsonl --contract stream-perf-analysis/examples/audio-contract.json`。
- **预期结果**：样例 `valid_windows=1`，`read_audio/filter_audio` 均值 3.0 ms；真实输入输出有效窗口、丢弃原因及可推导统计。
- **失效条件**：缺报、重连、计数回退和单位不符时断开窗口；缺乏分布数据时不产生分位数。该工具分析已有数据，不自动采集板端性能。
- **验证与经验**：已有累计快照、音频/传感合成复用与拒绝用例，见[格式说明](../stream-perf-analysis/references/log-formats.md)、[P07](pitfalls.md#p07-performance)。

## fpga-verification-gates

- **适用场景**：RTL/AXI、时钟/复位、CDC、资源/时序或制品身份阻塞交付。
- **最小输入**：规范 HDL/参数/XDC、实际构建入口、输入模型、已有真实报告和拟验证的判断。
- **使用**：读[验证入口](../fpga-verification-gates/SKILL.md)，使用其中 `使用 $fpga-verification-gates` 提示词；按[验收模板](../fpga-verification-gates/references/acceptance-template.md)填记录。这里没有独立的一键通用黄金比较器。
- **预期结果**：得到有输入、判据、实际输出、证据路径和范围的验收表；先选最便宜且能证伪问题的检查。
- **失效条件**：旧 OOC、截图、缺失/未知报告不能签署新顶层；修改约束或豁免必须有依据。
- **验证与经验**：已有分层方法和历史案例；跨题构建数据见[验证记录](validation-results.md)，报告与阻塞解释见[P06](pitfalls.md#p06-reports)、[P08](pitfalls.md#p08-blocked)。

## xilinx-project-flow

- **适用场景**：确定用户态、Overlay、硬件构建或启动制品中的当前工作阶段。
- **最小输入**：实际工具/板卡/系统版本，目标产物，已有 BIT/HWH；涉及平台/启动再给 XSA/ELF/BOOT 身份。
- **使用**：读[阶段入口](../xilinx-project-flow/SKILL.md)，填写 `使用 $xilinx-project-flow` 提示词；按需要选择其制品链和阶段参考。
- **预期结果**：给出当前阶段的输入、运行入口、预期产物、通过条件和下一门槛；用户态修改可复用已核准硬件。
- **失效条件**：平台、ABI、制品代次或恢复条件未知时先补证据；新板检查表不等于已有 BSP/设备树/镜像适配。
- **验证与经验**：阶段组织参考 xilinx-suite；已有案例与本轮候选工程构建记录，跨板范围见[验证表](validation-results.md#package-scope)。

## ray-game-integration

- **适用场景**：实物类别/位置/方向进入权威场景、光路与交互呈现。与图像定位/场景提交有关的部分按目标项目适配。
- **最小输入**：现有检测/求解/渲染入口、唯一配置、坐标变换、观测时间/序号/关卡代次及一个触发样例。
- **使用**：读[场景入口](../ray-game-integration/SKILL.md)，填写其中 `使用 $ray-game-integration` 提示词；沿一个观测检查到场景与显示的完整路径。
- **预期结果**：定位坐标、时间有效性或一致性断点，交付对应修改及旧帧/遮挡/旋转等适用反例。该项没有脱离目标工程的一键独立 CLI。
- **失效条件**：缺标定、语义或生命周期证据时保留未知；显示保持不作新鲜观测，不能改模板/求解器制造通关。
- **验证与经验**：仅有[历史记录](project-evidence.json)中的 host/Godot 回归；本次三题没有独立评估该技能。

## 替换项目与板卡时

换题先替换接口契约、数据格式、输入样例和正确性判据，再对齐驱动。换板再核准 part、DDR/MIO、时钟/复位、镜像、PYNQ/Python/ABI、分配器与地址能力。当前跨题实验使用同一器件/工具链；跨板硬件运行尚未验证。

包内[验证记录](validation-results.md)用于说明适用范围和已知缺口，按需读取；普通开发任务不默认加载整份实验数据。
