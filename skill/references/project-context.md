# 2026-10-28历史工程适配示例

快照日期：2026-10-28。以下是当时保留的工程事实，不代表当前运行状态，也不是PYNQ迁移的默认配置。本轮采用现有Linux/PYNQ路线；当前目标/状态以PROJECT_STATE.md和最新用户决定为准，通用开发读 [PYNQ入口](../pynq-development/SKILL.md)。本文件保留历史证据，不作为第二份运行配置。

## 历史运行路线与入口

- 历史板端：Cortex-A9/core0 Standalone，`color_test/software/vision_ps_baremetal/src/standalone/game_beam_standalone.c` 与 `game_baremetal_io.c`。这是当时的入口，不作为本轮Linux/PYNQ开发或交付依赖。
- 检测：同一 `vision_ps` 的 `restored_markers` profile。Mirror 黄色主体+黑端点；Portal 蓝/橙主体+白色实心点/圆环，轴从 solid 指向 ring；Wall 两端白条；Target 绿色圆。AprilTag 源与旧尺寸记录只作历史，不自动启用。
- 共享核心：同一 `vision_stabilizer`、`game_session/ray_game` 和唯一 `pc_vision/game_config.json`。板端诊断与 PC 游戏共用算法，不表示已共享同局结算。
- PC：`pc_vision/godot_bridge.py` 的 BoardInput/BoardGamePresenter、`board_native.py` 的 NativeBoardGame、`board_wire.py` 的 BinaryParser、`board_control.py`、`board_pose.py` 与 `board_game_host.c`；前端为 Godot 和已有网页，共享单一串口运行层。
- 网页：原工程 `pc_vision(1)/pc_vision/shared_runtime.py` 加载根规范运行层；不复制检测器、配置或 C 状态机。线上协议说明在 `pc_vision/SERIAL_PROTOCOL.md`。

## 历史参数与互不替代的含义

| 参数/规则 | 历史快照值 | 含义 |
| --- | --- | --- |
| board_game.scene_max_age_ms | 350ms | PC 新场景准入；350ms 边界可接受，351ms 拒绝 |
| 校时区间质量上限 | 250ms | 独立的时钟质量约束，未随场景准入改为350 |
| real_scene.beam.stability_support_gap_ms | 350ms | 板端 B 稳定器连续支持间隔；351ms 重新确认 |
| real_scene.beam.max_age_ms | 0 | 当前板端无关卡测试不按帧龄拒绝/停机，仍保留原始时间与 DMA 规则 |
| 两端 portal_b_exit_side | 1 | solid→ring 轴正法向一侧长边，垂直向外出射 |
| PC 运行关卡显示保持 | 等待新完整场景 | 保留上一份模型/光路，原时序不变，不送回 C 得分；切关/菜单/结束清理 |
| 板端旧画面保持 | 从原 captured_ms 起至多6s | 同帧相机原图、模型、完整光段恒亮；STALE/无效不附旧姿态，不能得分 |
| 原始采集/游戏/HDMI坐标 | 1280×720 | 像素预览，未声称毫米标定；原始捕获时间不是已测曝光时间 |

## 协议与交付边界

线上全部消息为二进制 v3：00FF/COBS/长度/CRC32，保留相机 generation、sequence、capture/publish 和 PC level/generation/nonce。内部旧 POSE2/LEVEL2 字符串标签不表示线上仍是 v2；不自动降级。LEVEL 43 字节，3/5物体完整姿态106/130字节，理论线时不能当实测帧率。

历史固件 version14，BOOT 位于 `color_test/build/beam_standalone/restored_binary_v3_1/output/BOOT.BIN`；PC共享运行层 `20261028-binary-v3-350-6`、网页 `20261028-web-sync350-3`。当时构建用 `color_test/software/vision_ps_baremetal/tools/build_game_beam.tcl`，复用已配对冻结平台/FSBL/BIT；检查用 `verify_game_beam.py`。这些旧启动制品不作为本轮PYNQ应用更新的前置条件。

用户已反馈当前 version14 成功，但没有因此推断新 FPS 或新时序测量。原工程历史 host/ARM/BOOT/用户反馈分开记录；本轮只维护技能并执行离线脚本。证据快照见 [project-evidence.json](project-evidence.json)。
