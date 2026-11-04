# 第一关现场操作与原始串口记录

用户确认本轮完成：相机/HDMI启动 → 网页第一关 → 开始 → 实物交互 → 目标命中 → 结算。现场结果确认为 **3星、20秒多一点**；未提供现场结算截图或实时C状态快照。

此前同一聊天中，用户返回boot `444e75fd-4a10-4ca1-b62e-53c69d38ef91` 的硬件准入成功输出，并确认HDMI随手和物块动作实时更新。UART文件本身不含boot_id，以上属于用户提供的同轮上下文，不声称能由串口字节独立还原启动或HDMI画面。

## 原始文件

| 文件 | 来源与内容 |
| --- | --- |
| [host_terminal.txt](host_terminal.txt) | 用户上传的电脑终端全文，32706字节，按原始字节保留。 |
| [uart_original.jsonl](uart_original.jsonl) | 终端明确指出的实际UART日志，只读取回，103384字节、447条事件，包含339条RX_BYTES；原始字节保留。 |
| [verification.json](verification.json) | 原始文件SHA256、用户确认、版本、控制身份、解析与离线复核范围。 |
| [user_boot_qualification.json](user_boot_qualification.json) | 用户此前提供的同轮启动检查摘录与准入JSON，保留来源说明；不是可安装的受保护准入回执。 |
| [board_session.txt](board_session.txt) | 用户粘贴的板端持续运行Ctrl+C退出及三帧重启终端输出。 |

实际电脑入口为 `pc_vision(1)/pc_vision/start_game.ps1`，日志记录 `20261101-web-teaching-2 / 20261101-pc-teaching-2`，COM9、115200、二进制v3、场景准入600ms。提交包网页入口版本不同，保留这一身份差异。

## 原始数据能确认什么

| 环节 | 核对结果 |
| --- | --- |
| 选关 | LEVEL3指定关卡1，generation=1、nonce=4004784581，收到匹配READY3及光源回显。 |
| 开始 | 收到同一关卡/代次/nonce的STARTED3。 |
| 物理观测 | 还原66帧姿态，协议解析拒绝0；11帧OK、52帧PENDING、3帧UNAVAILABLE。各帧仍保留原始序号和采集/发布时间。 |
| 姿态变化 | 有效帧中的Mirror中心和有向轴发生变化；原始帧与用户报告的实物操作对应，不把观测变化当作数值姿态精度真值。 |
| 后续控制 | 同会话RESET3及RESET3ACK匹配。 |

日志中的LEVEL2/READY2等是内部接口名称，实际wire_name和字节流均为v3。启动初期14次SYNC超时原样保留；随后35次校时回复中24次接受、11次超过质量门限而拒绝。PENDING、无效场景、校时拒绝与坏包分别统计。

## C核心离线复核

[decoded_poses.jsonl](decoded_poses.jsonl) 是使用现有协议解析器得到的66帧数据；[offline_c_replay.jsonl](offline_c_replay.jsonl) 是用实际记录的控制和姿态、时钟区间以及提交版C核心生成的69份离线状态，**不是现场实时状态日志**。

离线首次结果：第一关目标命中，`game_state=3`、`success=1`、`stars=3`、`elapsed_ms=20181`，来自原始板端序号113。精确20.181秒只属于离线复核；用户现场确认保持为“3星、20秒多一点”。

实际电脑分支与提交版的board_game配置、game_session/ray_game C及头文件、C主机入口、协议解析器相同；BoardGamePresenter的AST相同；生成的game_config.c逐字节相同。board_native.py仅有注释和MSVC `/utf-8`编译参数差异。用实际分支C程序和提交版C程序分别重放后，69份状态全部相同。这支持同一游戏判定核心的结果一致性，不将实际运行的旧网页版本改标为新版本。

在提交包根目录复现，使用新输出目录：

```powershell
python -X utf8 -B sim/replay_serial.py --project src/project --trace board/evidence/level1_run_1/uart_original.jsonl --output replay_serial_output_1
```

脚本不打开UART、不访问板卡；复用现有C进程和呈现控制器。QUEUED记录映射为选关/开始/菜单输入，按记录事件时间更新；校时接收时刻由记录的RTT还原。现场约10ms轮询的精确调度时刻未被记录，复核输出按其离线执行范围解释。

## 安全退出与同boot重启

用户补充的连续命令输出显示：持续运行提交4159帧，Ctrl+C后返回提示符，`can_exit=true`、`first_fault=null`；随后运行 `--frames 3` 提交3帧并正常返回，同样 `can_exit=true`、`first_fault=null`。同boot关联来自连续操作和此前准入上下文，退出JSON本身没有boot_id字段。两份报告均按用户提供的stdout保存，不表述为主机直接取回的板端文件。

退出流程在相关DMA停机确认后才释放缓冲；can_exit是当前运行所有者的资源释放状态。本轮无需再以电脑退出阶段的KeyboardInterrupt推定板端状态，已另有实际板端退出报告。电脑原始堆栈仍保留。

| 持续运行退出前窗口 | 样本数 | 均值ms | 中位数ms | 最大值ms |
| --- | --- | --- | --- | --- |
| 采集与复制 | 256 | 181.457 | 176.946 | 242.323 |
| C处理与组帧 | 256 | 91.396 | 89.100 | 112.505 |
| 显示提交与退休 | 256 | 39.073 | 38.284 | 56.320 |

这些值只描述最后最多256个实际样本，不能写成4159帧全程均值、第一关20秒窗口均值或实测FPS。三帧重启中采集/处理各3个样本、显示退休2个样本：frames在成功提交时增加，display_ms只在退休完成时追加；达到帧数上限后，最后一次提交可由安全停机收尾，不表示3次都完成常规退休。

## 验证范围

本轮第一关现场操作、原始UART、同C核心离线复核、持续运行安全退出及同boot短重启已形成记录。未据此扩展为全部关卡或数值姿态精度。PL同次综合/实现报告与时序结论仍按既有构建说明处理。
