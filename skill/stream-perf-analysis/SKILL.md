---
name: stream-perf-analysis
description: 分析已有流式日志的累计耗时、吞吐与新鲜度，识别重连和计数回退；用于性能定位，不将界面刷新率当作识别吞吐。
---

# 流式日志性能分析

适用于视频、音频、传感或推理流水线。只分析已有日志；本任务不因分析而改协议、阈值、重启进程或采集新硬件数据。

## 按任务读取

- 分析累计快照：读取 [输入格式](references/log-formats.md)，优先运行现有分析器；完整换题示例见 [传感器案例](references/sensor-walkthrough.md)。
- 分析原项目串口事件：按需读取 [工程适配](../references/project-context.md)，使用目标工程的规范协议解析器。
- 评价技能效果：由实验组织者读取 [对照实验方法](evals/protocol.md)。普通日志分析不加载评分标准。

## 使用方法

1. 先选择要解释的指标：源采集间隔、检测耗时、有效提交率、接收间隔、队列年龄、界面采用或端到端延迟。分别说明单位、时钟域和测量边界。
2. 选同一连接/启动区间的连续原始记录。关联 generation、sequence、captured time、level；计数回退、重连、缺报告时不跨界计算。跨设备有映射区间才能计算保守年龄，接收时间不代替采集时间。
3. 区分 leaf、envelope、span、event、meta；累计快照用差分计算窗口样本数和均值。重叠阶段不能直接相加。累计最大值一般不能确定窗口最大值；若同一连续累计区间的新最大值严格增大，则它就是该窗口最大值。分位数须先明确样本数和定义，不能无条件否定可推导的特例，详见输入格式。
4. 区分无新包、无效观测、物体缺失、稳定器 PENDING、过期、断线与显示保持。解析器诊断计数需要按实际报文解析结果解释，不能见到 REJECTED 就算丢姿态。
5. 输出可比较窗口、样本数、均值和异常边界，再给出证据支持的瓶颈判断与最小下一步。最慢阶段不自动是系统瓶颈；缺少周期、排队或阶段包含关系时，具体说明尚缺的证据。保持显示或提高 UI 刷新不代表识别变快。

## 累计统计格式：可直接运行

脚本要求每行包含 `connection, report, stage, n, total, maximum`；测量阶段的 `unit` 必须为 `us`。配置、退出码和限制见 [输入格式](references/log-formats.md)。

```text
python -B stream-perf-analysis/scripts/analyze.py stream-perf-analysis/examples/performance.jsonl --contract stream-perf-analysis/references/project-perf-contract.json
python -B -m unittest discover -s stream-perf-analysis/scripts -p test_analyze.py
```

以上命令从技能包根目录（含本技能子目录和 README.md）执行；当前仓库先进入 `大赛文档/skill/.skill/`，独立复制后使用实际路径，不要求目录名为 skill。

预期 1 个有效窗口，报告 24→25、25 个可比非 meta 阶段和 6 个 meta 阶段；13 个测试覆盖缺报、重连、计数回退、单位/计数非法、CLI 只读及另一题目。换成包内 `audio-performance.jsonl` 与 `audio-contract.json` 可直接复现音频题目的合成窗口均值，无需修改脚本。分析器仅保留最后一个有效窗口的详细指标；需要所有窗口时，按原始边界分段分析。

## 原始 UART/v3 日志：先识别格式

当前工程串口 JSONL 是 `event/time_ms/epoch/data_hex` 等事件与二进制帧，不能直接传给上述累计统计分析器。先使用目标工程同一协议解析器关联完整帧、会话与诊断；没有可靠映射就只报告同域指标。不为了凑格式将 PC 接收时间重命名为 capture，也不把内部旧 `POSE2` 标签当作线上 v2。原工程 v3 入口见可选适配，通用技能包不复制协议实现。

## 可复制提示词

```text
使用 $stream-perf-analysis。已有日志：填写路径；要回答的问题：填写指标和症状。
说明输入格式、单位、时钟来源、连接/启动边界以及哪些阶段重叠。
仅从已有数据计算；先检查数据可比性，输出有效窗口、样本数、指标和异常边界。
有证据再判断瓶颈；缺证据时说明缺项并给最小下一步。
不要改阈值；明确统计定义与推导条件，不把界面 FPS 当作有效识别频率。
```

## 失效条件、经验来源与效果

日志格式不匹配、时钟域不明、原始帧标记缺失或只有累计最大值时，不能给出不受支持的端到端延迟或分位数。默认分析器不自动适配任意日志，也不证明曝光到显示延迟。

原工程历史 v2 日志中 `CONTROL_RX_REJECTED` 可由正常姿态分片触发，POSE 解码仍成功；近期分析把源采集、检测、防抖和校时区间分别量化，未将它们混成一个 FPS。证据见 [project-evidence.json](../references/project-evidence.json) 的 `pc_portal_b_alignment_perf_20261028` 与 `v3_levels_latency_analysis_20261028`。保留的 62 行累计样例可复现其对应的 25 个非 meta 阶段差分；音频样例和边界测试是合成 host 验证，不是跨板实测。
