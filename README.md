# PYNQ 与网页光路交互系统

本目录汇集 version14 光路交互系统的工程源码、板端运行文件、构建脚本、离线回放数据、技能包和协作记录。系统以摄像头画面中的实物姿态驱动光路计算，提供板端 HDMI 实景叠加和电脑浏览器虚拟游戏两种呈现。

当前包收录第一关用户现场确认、原始UART、同C核心离线复核及安全退出证据。新PL候选已完成综合、实现和同次报告，并从同一布线检查点导出BIT/HWH/XSA，建立[源码—检查点—报告—Overlay同源关系](build/overlay_candidate/binding.json)。新Overlay见[候选目录](build/overlay_candidate/)。

画面采用 1280×720 分辨率。交互物体包括反射镜 Mirror、传送门 Portal A、传送门 Portal B、目标 Target 和障碍物 WALL；光源位置与初始方向由配置定义。

## 系统组成

| 部分 | 内容 |
| --- | --- |
| PYNQ 板端 | Python 管理 Overlay、相机、MMIO、GPIO、采集与显示缓冲，并调度 C 接口。 |
| C 核心 | 处理物体检测、姿态稳定、场景提交、光路求解、显示保持和游戏会话。 |
| 电脑后台 | 接收串口 v3 二进制消息，处理控制握手、时钟映射和游戏状态，并向网页提供数据。 |
| 网页界面 | 使用 Three.js 呈现关卡、物体模型、光路、交互效果、计时和结算。 |

## 目录结构

```text
pynq_web_v14/
├── README.md
├── src/        工程源码与配套资源
├── build/      构建脚本、工具依赖及综合实现报告
├── board/      板端运行文件与运行记录
├── sim/        主机检查与图片回放脚本
├── data/       参考图片、测试图片、索引与回放结果
├── skill/      一项通用 DMA 技能及配套资源
└── report/     PDF 协作记录与复现说明
```

## 目录命名与表格文件

本包目录名已去掉日期。历史日志、JSON、执行脚本和 PDF 中的日期及原始命令保持原样；复现请使用本 README 和 `build/pl_flow.md` 中的当前路径。

TSV 是制表符分隔的文本表格，内容不是图标。资源管理器显示的图标由默认打开程序关联决定。本次删除 28 个重复清单、历史阶段清单和状态摘要，保留以下 17 个文件：

| 用途 | 数量 | 保留原因 |
| --- | --- | --- |
| 测试图片与 HDMI 截图索引 | 2 | 保存样本编号、文件摘要和数据用途；图片回放读取测试索引。 |
| 当前构建的输入、暂存输入、输出、状态和时序校验 | 6 | `build/export_overlay.py` 校验当前源码、检查点与报告时使用；保留在 `build/reports/sampling_window_build/`。 |
| 详细时序与采样分析结果 | 9 | 保留时序与采样分析结果及路径明细，便于核查。 |

源码、运行文件、原生报告及检查点均保留。完整原包另存于仓库的 `output/build/game_app/submission_cleanup_1/pynq_web_v14_before_cleanup.zip`，不随精简提交包重复分发。历史记录中的原始清单摘要对应该归档；未将精简目录冒充完整的原始构建输出。以后重新构建时，脚本仍会生成正常的 TSV 校验和状态文件。

## 工程源码

源码集中在 [src/project/](src/project/)，文件引用已与包内的小写路径统一，可直接作为工程根目录使用。电脑端从该目录运行 `start_web.ps1`；构建和回放脚本的 `--project` 参数指向该目录。技能包可直接使用 [skill/](skill/)。

| 路径 | 内容 |
| --- | --- |
| [src/project/pynq_vision/](src/project/pynq_vision/) | PYNQ 硬件编排、C 库调用、相机参数、采集、内存管理和 Notebook。 |
| [src/project/color_test/software/vision_ps_baremetal/src/](src/project/color_test/software/vision_ps_baremetal/src/) | 检测与游戏 C 核心，包括 `vision_ps.c`、`game_beam.c`、`game_session.c`、`ray_game.c` 和 `pynq/` 平台接口。 |
| [src/project/pc_vision/](src/project/pc_vision/) | 串口控制、姿态与协议处理、C 会话桥接及共享配置。 |
| [src/project/pc_vision_1_/pc_vision/](src/project/pc_vision_1_/pc_vision/) | 网页后台、共享运行层、启动脚本与网页资源。 |
| [src/project/pc_vision_1_/pc_vision/web/](src/project/pc_vision_1_/pc_vision/web/) | 网页入口 `index.html`、主逻辑 `main.js`、样式 `style.css`、传送门效果和呈现逻辑。 |
| [src/project/pc_vision/game_config.json](src/project/pc_vision/game_config.json) | 关卡、固定光源、场景准入、稳定参数和光路规则的共享配置。 |
| [src/project/deployment/](src/project/deployment/) | 板端部署与运行准入工具源码。 |
| [src/project/color_test/rtl/](src/project/color_test/rtl/) | PL 参考 RTL。 |
| [src/project/color_test/color_test.xpr](src/project/color_test/color_test.xpr) | Vivado 工程文件。 |
| [src/project/start_web.ps1](src/project/start_web.ps1) | 电脑网页系统启动入口。 |
| [src/project/pc_vision/serial_protocol.md](src/project/pc_vision/serial_protocol.md) | 串口 v3 消息格式与交互协议。 |

## 板端运行文件

[board/runtime/](board/runtime/) 集中保存板端入口、Python 模块、Notebook、原生库和 Overlay 文件。

| 路径 | 内容 |
| --- | --- |
| [board/runtime/beam_v14.py](board/runtime/beam_v14.py) | 板端统一命令入口，提供信息检查、运行准入和会话启动功能。 |
| [board/runtime/beam_v14_deploy_v2.pyz](board/runtime/beam_v14_deploy_v2.pyz) | 部署工具归档。 |
| [board/runtime/beam_v14_ready_v2.pyz](board/runtime/beam_v14_ready_v2.pyz) | 运行准入工具归档。 |
| [board/runtime/pynq_vision/beam_hardware.py](board/runtime/pynq_vision/beam_hardware.py) | 硬件所有者与采集、处理、显示调度。 |
| [board/runtime/pynq_vision/beam_runtime.py](board/runtime/pynq_vision/beam_runtime.py) | C 原生库接口及运行数据封装。 |
| [board/runtime/pynq_vision/notebooks/beam_v14_pynq.ipynb](board/runtime/pynq_vision/notebooks/beam_v14_pynq.ipynb) | Jupyter Notebook 交互入口。 |
| [board/runtime/output/build/game_app/pynq_beam_hardware_5/](board/runtime/output/build/game_app/pynq_beam_hardware_5/) | `libbeam_pynq.so`、`system_wrapper.bit`、`system_wrapper.hwh` 和 `hardware.json`。 |
| [board/evidence/](board/evidence/) | 系统检查、运行准入和十帧会话的 JSON 记录。 |
| [board/evidence/level1_run_1/README.md](board/evidence/level1_run_1/README.md) | 第一关现场用户确认、原始电脑终端和UART、逐帧解析及分开标注的C离线复核。 |

板端运行环境为 PYNQ 2.6.2、Python 3.6.5 和 ARMv7 Linux；原生库面向 Cortex-A9 硬浮点 ABI。

## 构建与离线回放

| 路径 | 内容 |
| --- | --- |
| [build/build_c.py](build/build_c.py) | PYNQ ARM 原生库和电脑端共享 C 核心的构建入口。 |
| [build/run_pl.py](build/run_pl.py) | 隔离输入、核对相机/IP模型、记录源与暂存摘要；支持仅验证、仅报告和受时序门槛保护的硬件导出。 |
| [build/export_overlay.py](build/export_overlay.py) | 从已验证报告的原始布线DCP导出并校验新Overlay；支持包内归档报告作为输入。 |
| [build/overlay_candidate/](build/overlay_candidate/) | 新BIT/HWH/XSA、可移植同源索引和原始导出证据；未替换板端运行目录。 |
| [build/build_pl.tcl](build/build_pl.tcl) | 综合、实现、资源/时序/CDC/DRC 报告、检查点和 BIT/XSA 导出 Tcl。 |
| [build/pl_flow.md](build/pl_flow.md) | PL 构建命令、统一 XPR 输入、恢复来源与硬件文件索引。 |
| [build/toolchain.txt](build/toolchain.txt) | Python、编译器、依赖库和目标运行环境版本记录。 |
| [build/requirements_host_locked.txt](build/requirements_host_locked.txt) | 主机依赖版本。 |
| [build/reports/raw/](build/reports/raw/) | 2026-10-13 历史综合/实现报告。 |
| [build/reports/camera_model_reanalysis/](build/reports/camera_model_reanalysis/) | 按最终相机名义模型重读既有routed DCP的真实STA结果、32组/128条路径、日志及输入摘要；hold仍FAIL。 |
| [build/reports/sampling_window_build/](build/reports/sampling_window_build/) | 当前`pr4`同次构建报告与检查点、两种包络的32组路径检查及输入身份。 |
| [build/reports/final_camera_build/](build/reports/final_camera_build/) | 校正源码`pr1`实际综合/布局布线的同次资源、时序、CDC/DRC报告、检查点、执行脚本和输入身份；报告完成、时序FAIL。 |
| [build/reports/windows_loader_fix/](build/reports/windows_loader_fix/) | `pl3`工具规则读取失败与`pv4`实际准备验证通过的原始日志，保留启动/隔离修复证据。 |
| [build/check_camera_timing.tcl](build/check_camera_timing.tcl) | 固定IDELAY与路由，只在内存替换相机时序模型并重新检查setup/hold的电脑端入口。 |
| [sim/run_checks.py](sim/run_checks.py) | PYNQ 运行层、部署工具、串口协议和网页的主机检查入口。 |
| [sim/replay_photos.py](sim/replay_photos.py) | 参考图片的 C 检测与光路回放。 |
| [sim/replay_test_data.py](sim/replay_test_data.py) | 按图片索引生成检测模型、光段、对照图和统计结果。 |
| [sim/test_data_probe.c](sim/test_data_probe.c) | 图片回放所用的 C 检测与场景输出接口。 |
| [sim/replay_serial.py](sim/replay_serial.py) | 只读原始UART事件，复用同一C核心重放选关、开始及姿态；不访问板卡。 |

## 数据与协作记录

| 路径 | 内容 |
| --- | --- |
| [data/reference/](data/reference/) | 图片回放参考素材。 |
| [data/results/replay_2/](data/results/replay_2/) | 参考图片的检测、光路和图像对照结果。 |
| [data/reference_results/hdmi/](data/reference_results/hdmi/) | 16 张 HDMI 实景叠加参考截图及索引。 |
| [data/reference_results/web/](data/reference_results/web/) | 17 张网页参考截图。 |
| [data/test_data/raw/](data/test_data/raw/) | 21 张算法测试图片：`01.png` 至 `20.png` 对应样本43至62，`42.png` 为空场图。 |
| [data/test_data/index.tsv](data/test_data/index.tsv) | 测试图片编号、文件摘要、尺寸、物体类别和摆放信息。 |
| [data/test_data/derived/replay_1/](data/test_data/derived/replay_1/) | 测试图片回放的模型、光段、对照图和汇总数据。 |
| [report/大模型协作记录.pdf](report/大模型协作记录.pdf) | PYNQ 实现协作记录，包含实现过程、阶段耗时图和图片检测结果。 |
| [report/复现说明.pdf](report/复现说明.pdf) | 从硬件准备、PYNQ 部署到网页游戏运行的操作步骤，附源码构建和图片回放命令。 |
| [report/FPGA创新设计大赛.pdf](report/FPGA创新设计大赛.pdf) | 比赛资料，按当前目录原样保留。 |

## 技能包

[skill/README.md](skill/README.md) 只保留一项通用 DMA 布局与安全退出技能，包含适用范围、使用方法、18 项主机检查及失效条件。其余扩展技能和独立 HLS/RTL 演示模板已归档到提交包之外。

## 比赛提交范围与待完成项

依据所提供指南 3.3 节，初级组与高级组的提交内容相同。本包保留实际采用的 RTL/PS/PYNQ/网页源码、验证输入与参考输出、板端运行文件、构建脚本、技能、设计与协作说明。无需为本次交付增加 HLS 加速器、其他板卡适配、新游戏功能或额外测试样本。工具固定 Vivado/Vitis 2023.1；指南允许其他版本，前提是说明版本并保证脚本可复现。

当前唯一配置为 `src/project/pc_vision/game_config.json`：场景准入 600 ms，B 防抖支持间隔 350 ms。这两个参数独立。旧技能中的配置快照已随扩展材料移出本包。

程序修复：显示提交最多重试 500 ms；退休包含错误在内共用原 500 ms 期限。两处循环均处理停止请求，随后进入实际 DMA 停机确认流程；无法确认停机时继续保留所有者和缓冲。修复覆盖源码与 `board/runtime/` 两处运行文件，现用 BIT/HWH/XSA、C 库、相机参数和 JSON 保持冻结。

电脑端PL交付状态如下：

| 工作 | 执行位置 | 完成依据 |
| --- | --- | --- |
| 新PL候选及同源Overlay | 电脑 Vivado | `pr4`实际综合/实现报告与`px2`导出的BIT/HWH/XSA已建立[同源对应](build/overlay_candidate/binding.json)。 |

原运行Overlay已完成的上板验证：

| 任务 | 要保留的结果 |
| --- | --- |
| 使用最终冻结的运行目录完成当前 boot 准入和相机/HDMI 启动 | 软件与 Overlay 身份、boot_id、原始准入输出、连续有效帧和 HDMI 记录。 |
| 第一关选关 → READY → STARTED → 实物交互 → TARGET 命中 → 结算 → 重置 | 本轮已有用户现场确认及原始UART。现场为3星、20秒多一点；离线C复核为3星/20181ms，未将离线状态充作实时状态。 |
| 持续运行Ctrl+C退出及同boot三帧重启 | 用户返回4159帧/3帧两份报告，均can_exit=true、first_fault=null。原始stdout及统计范围见第一关证据。 |

持续显示错误已有主机注入覆盖，本轮不要求人为制造硬件错误。

现有十帧记录仅证明该窗口的采集、处理、显示与安全退出。21/21 仅表示保留静态样本的物体类别名单一致，未测数值姿态精度、动态稳定或游戏成功率。HDMI 与网页参考截图未同步，不用于同帧几何比对。

第一关原始日志另存于 [实测记录](board/evidence/level1_run_1/README.md)：实际入口为20261101教学网页分支；与提交版游戏配置、C判定核心和场景提交器一致，同一原始输入在两份C程序的69份离线状态均相同。用户确认了现场命中结算；精确20181ms来自离线复核，未收到现场实时结果JSON或截图。

协作记录见 [report/大模型协作记录.pdf](report/大模型协作记录.pdf)，操作步骤见 [report/复现说明.pdf](report/复现说明.pdf)。PL 源码构建、新Overlay导出和同源核对以 [build/pl_flow.md](build/pl_flow.md) 为入口。

系统镜像来自 ALINX 官方配套资料，经百度网盘取得，由队伍确认来源；该来源说明不表示本次重新从网络下载。复现时向 ALINX 官方获取 AX7Z020B 对应的 PYNQ 镜像，再核对下列原始 IMG 摘要。本包不附带约6 GB的系统镜像。

镜像文件名为 `ax7z020b-2.6.0.img`，与运行中 PYNQ 2.6.2 的软件版本分别记录。原镜像长度 6140747776 字节，SHA256：

```text
bcee01b865196f8f433e4d17dc8d854d428c1c0a462c6080ba29c022524f1edd
```

本轮重新读取本地原始 IMG，确认长度和 SHA256 与先前提取目标 GLIBC 链接库时记录的一致。
