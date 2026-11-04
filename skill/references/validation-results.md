# 已验证效果与范围

本页记录已有实验，不代表本轮文档整理重新运行了模型或 FPGA。使用方法见[复用说明](reuse-guide.md)，已知问题见[踩坑清单](pitfalls.md)。

## cross-task-experiment

2026-11-02，在原有乘加器题目之外新增三类项目：周期控制/中断、AXI-Stream 字节变换与 DMA、BRAM 查表与 NumPy 批量接口。每类每组一个项目，最多一次首稿和一次失败反馈修复，共 12 次模型调用。模型为 `gpt-6-luna / medium`。

两组使用相同任务、可信 PS7 板级输入、Vivado 2023.1、`xc7z020clg400-2`、100 MHz 请求时钟、验收器与修复额度。有 Skill 组按固定任务路由注入当前包的相关文本，分别 11/15/13 份；无 Skill 组不注入这些资源。模型以结构化文件交付，未获得工具、私有验收器或参考实现访问权。

### 最终结果

| 新项目 | 无 Skill：已通过/10 | 有 Skill：已通过/10 | 有 Skill 的实际完成范围/剩余问题 |
| --- | --- | --- | --- |
| event_timer：周期控制与中断 | 0 | 10 | 实际准备、RTL/CPU、综合、实现、BIT/HWH/XSA 与完整交付均通过 |
| packet_xor：AXI-Stream/DMA | 3 | 8 | 实际硬件构建与导出通过；CPU 模拟恢复契约及依赖它的完整交付项未过 |
| bram_lookup：BRAM/NumPy | 1 | 5 | RTL 与准备通过；综合完成但 BRAM 原语为 0；取消后 IRQ 对象拒绝项未过 |
| 合计/宏平均 | 4/30，13.3% | 23/30，76.7% | 三类等权，每类每组只测一个项目 |

| 指标 | 无 Skill | 有 Skill |
| --- | ---: | ---: |
| 完整交付成功项目 | 0/3 | 1/3 |
| 实际硬件准备/综合/实现/导出全部通过的项目 | 0/3 | 2/3 |
| 新功能、协议、复位/错误路径与 CPU 驱动项 T02～T05 | 4/12 | 10/12 |
| 工程入口与交付项 T01、T06～T10 | 0/18 | 13/18 |
| 模型调用/修复次数 | 6/3 | 6/3 |
| CLI 报告累计 input+output token | 141864 | 217763 |
| 其中 cached input token | 26496 | 0 |
| 模型生成累计秒数 | 293.501 | 312.126 |
| 工具命令累计秒数 | 204.830 | 2242.343 |

本批观察到新控制任务和流式 DMA 的硬件构建收益；BRAM 映射、IRQ 取消及 DMA 恢复约定仍有未闭合项。token 增加约 53.5%，模型生成时间增加约 6.3%。工具耗时包含实际执行到的不同阶段，无 Skill 均提前停止，不据此计算成功项目的加速比；token 计数包含材料/共同 CLI 上下文与缓存，不是费用金额。

### 如何读分数和阻塞

每项目按 10 项等权判定：T01 工程入口、T02 功能、T03 总线/流协议、T04 复位/中断/错误、T05 CPU 驱动、T06 IP/BD、T07 目标综合要求、T08 实现门、T09 制品、T10 完整交付。每项必要子检查全部通过才计 1；主指标为已通过数/10，包含前置阻塞的影响，不是已执行检查的通过率，也不是独立错误数量。

前置功能/IP 准备失败时停止综合；映射要求不合格时停止实现/导出。T10 是最终交付判定。最终记录有 15 个被前置条件阻塞的格子：三个无 Skill 项目的 T07～T10，以及有 Skill BRAM 项目的 T08～T10。原始实验记为 NOT_RUN，包内显示列记为 BLOCKED，评分未修改。

### 判据分歧与环境记录

- DMA 的一个 CPU 子检查要求：模拟错误位仍置位、两通道允许 HALTED 后，`recover_if_idle()` 返回 True。候选继续保留 unknown 与两个缓冲，诊断未观察到提前释放。这涉及保守恢复与模拟器恢复条件的分歧；本批保留原分数，不将该失败改写为不安全释放。
- BRAM 私有参考最初综合成 LUTRAM；修改读地址后 727 项仿真断言通过。用户允许的第二次最小 OOC 在读取生成的 realtime Tcl 时失败，物理参考未完成验证，两个额度均保留。候选真实 BRAM 要求没有放宽，其综合记录实际为 0 个 BRAM 原语。
- 控制题有 Skill 首稿曾因 Vivado 读取自带 IP Tcl 失败而阻塞；修复轮的实际通过结果单独保留。四份修复稿的首次执行请求还曾被自动审批超时挡住，进程未启动；单次重试后执行，未新增模型调用。
- 两组模型源码和冻结技能材料均未人工修改。数据夹具的非连续数组/延迟 DMA 说明在对应题目调用前修正，原记录保留；未按候选成绩调整通过阈值。

### 包内数据与复算

- [逐项目数据](evidence/cross-task-projects.csv)：6 行，含首轮/最终结果、调用、token、时间、原记录相对路径与 SHA256。
- [汇总数据](evidence/cross-task-summary.csv)：2 行，保留原数值。宏平均可由三题 `final_rate` 求均值，或由 `final_completed` 之和除以 30 复算。
- [最终逐项状态](evidence/cross-task-checks.csv)：60 行，保留 `original_status`；`display_status` 仅把本批前置阻塞的 NOT_RUN 显示为 BLOCKED，T10 另标为 `final_verdict`。

CSV 可在脱离聊天/原实验目录时复算上述统计。完整模型/工具重跑另需原始实验材料、账户和实际工具环境；本包不复制模型调用器、私有评分器或硬件制品。原档索引为 `output/skill_project_eval_20261102_3/`：`protocol.json`、`review.json`、`summary.json`、`final_audit.json`、`dma_recovery_diagnostic.json`；候选记录为 `output/pe3/c{1,2,3}{b,s}{1,2}/result.json`。原路径仅是档案索引，不是使用技能的运行依赖。

## package-scope

| 对象 | 已有证据 | 尚未验证/已知限制 |
| --- | --- | --- |
| 离线检查/示例 | 原包 65 项检查、新增 RTL 分支 9 项检查分别通过；元数据/链接已有记录 | 4 项真实 C ABI 检查因缺少 GCC/Clang 跳过；不等于目标 ARM/PYNQ ABI 已通过 |
| pynq-development | HWH/数组契约有离线正反例；参与整体跨题材料 | 没有完整 register_map 教程；跨题数据不是该技能的单项因果效果 |
| pynq-accelerator-flow 的 add32 模板本体 | 2023.1/xc7z020clg400-2/100 MHz：准备通过，RTL 121 项断言通过，顶层及 6 个必要 IP OOC 综合通过 | 本体实现/导出停在当轮中断处；gate 尚有 CDC 短格式兼容缺口；HLS 工具运行未验证 |
| 跨题模型候选工程 | event_timer、packet_xor 实际综合/实现/导出通过，报告约束周期 10 ns，制品哈希核对通过 | 与 add32 模板本体验证分别记录；BRAM 候选映射要求未过 |
| pynq-dma-contract | 布局、行复制、所有权与有界停机有离线替身正反例 | 真实 PYNQ DMA 适配器、数据搬运、cache、错误恢复和退出尚未实板验证 |
| stream-perf-analysis | 已有累计快照、合成音频/传感输入与拒绝用例 | 只分析已有日志；不提供板端性能自动采集 |
| fpga-verification-gates、xilinx-project-flow | 已有工作流/模板；跨题实验检查真实工具对象和报告 | 未对单个技能做隔离归因；没有包内独立通用黄金比较器 |
| ray-game-integration | 工程历史 host/Godot 回归摘录见 project-evidence.json | 本批三题未单独评估该项 |
| 新板/系统迁移 | 有分支检查表；构建需调用者提供可信板级预设 | 跨板硬件、真实 IRQ、DMA/cache、镜像/冷启动尚未验证 |

较早原包记录：`output/build/skill_canonical_fullflow_20261102_1/`；add32 本体记录：`output/build/skill_rtl_completion_20261102_1/review.json`、`output/rtlv5/`。历史工程来源摘录为[project-evidence.json](project-evidence.json)。本页三题是整体材料对照，不能把 23/30 分别归因给七个技能中的任意一个，也不据此宣称获得赛事加分或任意 PYNQ 项目均可完成。
