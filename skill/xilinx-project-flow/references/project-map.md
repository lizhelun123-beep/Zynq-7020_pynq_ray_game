# 工程路径线索与历史入口

本轮面向Linux/PYNQ开发，先使用 [开发入口](../../pynq-development/SKILL.md)。下表保留2026-10-28旧路线的路径线索，不保证当前仍存在或代表当前运行状态；以目标项目和PROJECT_STATE.md为准。历史事实快照见 [project-context.md](../../references/project-context.md)，不作为迁移默认配置。

| 阶段 | 原工程路径 | 使用边界 |
| --- | --- | --- |
| 历史Standalone运行 | `color_test/software/vision_ps_baremetal/src/standalone/game_beam_standalone.c`、`game_baremetal_io.c` | 旧版本入口，不是当前PYNQ开发前置依赖 |
| 检测/稳定/光路 | `src/vision_ps.*`、`vision_stabilizer.*`、`game_beam.*`、`game_session.*`、`ray_game.*` | src 指上述 baremetal 目录；同一 C 核心 |
| ARM/BOOT 构建 | `color_test/software/vision_ps_baremetal/tools/build_game_beam.tcl`、`verify_game_beam.py`、`STANDALONE_BEAM.md` | 当前用 Vitis/XSCT2023.1；先核对冻结平台与新 tag |
| PC 共享运行层 | `pc_vision/godot_bridge.py`、`board_native.py`、`board_control.py`、`board_pose.py`、`board_wire.py`、`board_game_host.c` | Godot/网页共享配置、状态机和 C；同一时刻一个串口所有者 |
| 网页适配 | `pc_vision(1)/pc_vision/shared_runtime.py` 与现有网页入口 | 原路径是工程历史事实；提交技能包自身不用括号目录名 |
| 配置/协议 | `pc_vision/game_config.json`、`pc_vision/SERIAL_PROTOCOL.md`、既有 `generate_game_config.py` | 唯一手工 JSON；线上二进制 v3；不维护技能运行配置副本 |
| 规范硬件工程 | `color_test/color_test.xpr`、`color_test/color_test.srcs/sources_1/bd/system/system.bd`、`color_test/repo/ip/`、`color_test/color_test.srcs/constrs_1/new/` | 实际涉及 PL/BD/IP/XDC 时读取 |
| 硬件构建/导出 | `color_test/tools/build_bitstream.tcl`、`export_xsa.tcl`、`inspect_*.tcl` | 先选择最小检查，不默认运行完整实现 |
| Windows Vivado/JTAG | `color_test/tools/vivado_nocd.bat`、同目录 README 与 JTAG 脚本 | 遵循当前授权和唯一 hw_server 规则；不修改安装目录 |
| Linux/PYNQ定位线索 | `pynq_vision/`、原 `game_*linux*` 适配 | 按当前项目实际存在的入口核准，保留原生C核心与现有镜像 |

当前板为 AX7Z020B、`xc7z020clg400-2`，采集两 lane、1280×720 RAW10/BGGR。实际硬件接口、内存布局、缓存属性、时钟及运行版本仍以目标配置与产物来源为准。目录名 baremetal 下保留历史 Linux 文件，并不表示当前使用 Linux。
