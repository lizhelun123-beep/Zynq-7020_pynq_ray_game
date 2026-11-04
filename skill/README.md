# Linux/PYNQ应用开发技能包

版本：2026-11-02。面向现有Linux/PYNQ上的应用开发、Overlay/IP接入、Python/C接口及DMA/VDMA交接；保留摄像头交互项目提炼的专用方法。默认复用当前镜像、驱动与原生C核心。


## 技能选择与复用

新建/迁移PYNQ应用或跨模块任务先读pynq-development，再按其路由加载需要的参考与示例；已明确的布局、日志或PL问题可直接使用专项技能。每次先从已有文件确认实际环境，开发任务交付完整代码/调用/正反例，避免只输出审查清单。

| 技能 | 适用场景 | 使用方式与输入 | 失效条件/边界 | 经验来源与已验证效果 |
| --- | --- | --- | --- | --- |
| [pynq-accelerator-flow](pynq-accelerator-flow/SKILL.md) | 从 HLS 或自定义 RTL 新建 PYNQ Overlay、驱动与中断 | 提供实际 Zynq-7000 器件/PS7 预设/工具版本，按来源与阶段加载模板 | [RTL 路径与验证范围](pynq-accelerator-flow/references/rtl-flow.md)单独声明；其他架构、真实 IRQ 与冷启动需另验 | 参考 xilinx-suite 阶段组织及 PYNQ/AMD 官方接口，补充封装、路径、寄存器和制品绑定的正反例 |
| [pynq-development](pynq-development/SKILL.md) | Linux/PYNQ应用、Overlay/IP及Python/C接口开发 | 提供实际环境与BIT/HWH；按任务读取开发流程，运行HWH或数组示例 | 文件声明不证明硬件已加载；原生库与设备接口需实际ABI/驱动证据 | 参考xilinx-suite分阶段组织；新增文件解析、数组契约及正反例，真实板端仍待独立验证 |
| [ray-game-integration](ray-game-integration/SKILL.md) | 实物姿态驱动交互、固定发射条件、稳定和呈现一致性 | 提供实际入口、配置、坐标与一段观测，使用技能中的提示词 | 没有标定不能承诺毫米精度；显示保持不能代替新观测 | Portal B 两端策略不一致、遮挡清屏问题；历史 host/Godot 回归覆盖旋转、旧帧拒绝和原子替换 |
| [pynq-dma-contract](pynq-dma-contract/SKILL.md) | Linux/PYNQ采集、显示、加速器缓冲交接 | 提供格式、stride/span、实际所有权与驱动；运行布局检查或完整离线生命周期例子 | 替身/静态描述不证明真实同步、退休与设备停机 | PARK/指针误判的教训；新增源/目标步幅、有界停机、提交异常后保留所有权的可执行例子 |
| [stream-perf-analysis](stream-perf-analysis/SKILL.md) | 流式检测/传输/显示慢，区分新鲜度与吞吐 | 提供同一时钟域、连接和启动区间的已有日志；累计统计格式可直接运行分析器 | 分位数先明确样本数/定义与可推导条件；不能直接读取任意UART日志 | 历史计数误判与源流水线延迟；累计快照正反例和分位数特例已纳入说明 |
| [fpga-verification-gates](fpga-verification-gates/SKILL.md) | PL、AXI、Bayer、时序/CDC 或硬件制品直接阻塞功能 | 提供改动、实际输入和判据，选择能证伪问题的最低层检查 | 旧 OOC/截图不能签署新顶层；host 反例不能证明真实 RTL 已修复 | CRC 为零仍可能丢行；保留分层证据与 NOT_RUN/UNKNOWN，不用下游换色掩盖 Bayer 错误 |
| [xilinx-project-flow](xilinx-project-flow/SKILL.md) | PYNQ用户态、Overlay或硬件变更的阶段选择 | 提供实际环境、BIT/HWH、代码入口与预期产物；平台/启动任务另核XSA/ELF/BOOT | 用户态更新不默认重建PL/BOOT/系统；构建不等于板端通过 | 复用已有硬件、按阶段交付；旧Standalone制品经验仅作来源 |

每项的最小输入、命令/提示词、预期输出见[复用说明](references/reuse-guide.md)；按触发条件定位问题见[踩坑清单](references/pitfalls.md)；已验证效果、包内统计数据及未验证范围见[验证记录](references/validation-results.md)。开发时按需读取，不必把实验记录加载到每个任务。

技能入口说明方法、边界和按需读取路径；提示词及经验来源见对应说明。核心检查、HWH提取和DMA替身只需Python3.8+标准库；可选数组示例需要已有NumPy，自检会明确报告跳过，不自动安装。`agents/openai.yaml`是可选界面元数据，直接读取SKILL.md也可使用。

新增加速器模板的 Tcl 完整性检查使用标准库 tkinter/Tcl；Notebook 只做语法检查。C 库与 ctypes 模板并入 pynq-development，真实 C ABI 测试需要已有 NumPy 和 GCC/Clang；缺失明确跳过，不自动安装。RTL 加法器模板已有实际准备/仿真/综合记录；独立跨题候选中有两个项目完成实际硬件构建与导出，详见验证记录。HLS 工具运行、目标部署、真实 IRQ、异常恢复与冷启动仍需相应证据。

## 从零开始

1. 在技能包根目录（本 README 所在目录）打开终端，确认 `python --version` 为 3.8 或更高。当前仓库从工程根目录执行 `Set-Location -LiteralPath '大赛文档/skill/.skill'`；独立复制后进入实际目录，不要求目录名为 skill。
2. 运行整个技能包的离线自检：

   ```text
   python -B scripts/verify_package.py .
   ```

   成功时退出码为 0；检查技能元数据、包内链接、文件命名，并运行性能分析和 DMA 校验的正反例。不会连接设备、修改项目配置或启动 Vivado。
3. 选择上表对应技能，复制其中提示词，将“目标工程、输入和判据”换成自己的项目。运行脚本不是使用提示词工作流的前提。
4. 复用到新题目/板卡时，先替换本地适配参数；保留时钟、所有权、有效性和证据层次的区分。当前工程参数仅是 [可选适配示例](references/project-context.md)，不是其他团队必须采用的值。

本轮不生成ZIP。后续明确要求打包时，从当前技能包根目录指定本目录为源，并选择一个新的包外输出目录：

```text
python -B scripts/package_skill.py --source . --destination ../../../output/build/skill_pynq_package_20261101
```

目标目录须位于源目录外且未存放需保留的结果。打包时另行核准脚本的版本元数据；该入口未在本轮执行。它会生成skill子包、manifest、验证回执和ZIP，不包含运行工程。

## 可直接执行的复用例子

PYNQ离线开发示例（均从技能包根目录运行）：

```text
python -B pynq-development/scripts/inspect_hwh.py pynq-development/examples/synthetic.hwh --ip demo_dma
python -B pynq-dma-contract/examples/lifecycle.py
python -B pynq-development/examples/native_array.py
```

依次预期OFFLINE_DECLARATIONS_ONLY（地址窗口span=65536）、MOCK_LIFECYCLE_ONLY（明确停机后released）、MOCK_NATIVE_ONLY（输入不变）。最后一条需要已有NumPy，其他命令不需要PYNQ或NumPy。真实PYNQ驱动操作按开发流程和本轮授权单独核准。

原工程累计耗时样例，输入与配置位于包内：

```text
python -B stream-perf-analysis/scripts/analyze.py stream-perf-analysis/examples/performance.jsonl --contract stream-perf-analysis/references/project-perf-contract.json
```

预期：`valid_windows=1`，比较报告 24→25，共 25 个非 meta 阶段（另有 6 个 meta 阶段）。结果中的最大值仍是累计最大值，不是窗口分位数。

换成音频流处理题目，不改分析器，只换阶段配置与数据：

```text
python -B stream-perf-analysis/scripts/analyze.py stream-perf-analysis/examples/audio-performance.jsonl --contract stream-perf-analysis/examples/audio-contract.json
```

预期：`read_audio` 和 `filter_audio` 的窗口均值均为 3.0ms。这是合成复用用例，不是音频硬件实测。

DMA 布局检查示例见对应技能；它会验证包含行填充的分配长度、地址范围、重叠和声明的 CPU/device 访问冲突。

## 已验证效果

2026-11-02 新增控制/中断、AXI-Stream/DMA、BRAM/NumPy 三类完整工程对照，使用 gpt-6-luna/medium，每组每题最多一次反馈修复，共 12 次模型调用。最终任务完成率由无 Skill 的 4/30（13.3%）到有 Skill 的 23/30（76.7%）；完整交付为 0/3 对 1/3。该指标包含被前置条件阻塞的项目，并非只统计已执行项。

方法、token/耗时、逐项状态、判据分歧和数据下载见[验证记录](references/validation-results.md#cross-task-experiment)。这是三个项目的整体材料对照，跨板与真实 PYNQ 运行另行验证。

以下为较早的文本/替身实验，验证范围按各轮单独解释：

流式分析另有 [独立传感器案例](stream-perf-analysis/references/sensor-walkthrough.md) 与 [技能效果对照实验](stream-perf-analysis/evals/protocol.md)。案例数据为合成输入；第一轮发现并修正了最大值/分位数规则过于绝对的问题，修订版又完成18次gpt-6-luna/max文本对照，本组任务中两组质量指标持平。脚本工具收益与实板能力尚未测量。包内记录表保留为空白模板，实测证据位置见对照实验说明。

PL协议/验证、DMA布局/所有权、PS数组接口包装另各做6次gpt-6-luna/max代表任务对照。PL仅人工审查代码与证据；DMA仅离线契约分析；6份PS包装代码均通过13项NumPy/native替身检查。核心评分未显示稳定整体收益，DMA一份伪代码完整性有严格/宽松判分差异。任务、原回答、逐项评分、检查与图见工程 `output/skill_eval_20261101_3/review.json`；尚未验证HLS/顶层实现、实际DMA带宽、真实C ABI或板端FPS。

## 包含内容与验证解释

```text
skill/
  README.md
  references/                 # 要求对应、复用说明、踩坑、验证范围与证据CSV
  scripts/                    # 独立离线自检、布局检查和可复现打包
  pynq-development/           # Linux/PYNQ入口、HWH提取和Python/native示例
  pynq-accelerator-flow/      # HLS/BD分阶段模板、DefaultIP/IRQ/Notebook与部署验收
  ray-game-integration/       # 提示词工作流与场景验收方法
  pynq-dma-contract/          # 缓冲模板、布局脚本及正反例
  stream-perf-analysis/       # 累计日志分析器、数据与测试
  fpga-verification-gates/    # 分层校验工作流及证据模板
  xilinx-project-flow/        # 工具链路由、制品链与交接示例
```

目录名/文件名采用英文字符及数字、连字符、下划线和扩展名；`README.md`、`SKILL.md` 遵循技能入口命名。中文仅用于文件内容。包内链接可离线解析，原工程路径以代码文本列出，不要求原聊天或构建输出存在。

工程历史效果的原文摘录和来源 SHA256 在 [project-evidence.json](references/project-evidence.json)。其中 `historical_record` 是已有记录，`current_source` 是当时整理的配置/源码事实；与本次新增的跨题数据分别记录。完整历史日志和硬件制品未装入技能包；离线自检、模板综合、跨题候选构建和实板是不同验证层次。本轮仅整理文档和数据摘录，未重新执行这些测试；跨板硬件迁移尚未实测。

