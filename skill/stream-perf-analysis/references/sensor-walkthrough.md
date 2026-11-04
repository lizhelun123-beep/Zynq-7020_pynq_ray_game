# 独立传感器案例

目标：仅凭本技能目录分析一条传感器流水线，不需要原项目、PYNQ 或硬件。Python 3.8+，无额外依赖。数据为合成累计快照；`pipeline` 包含 `sample`，两者处理相同样本。

## 运行与验收

从技能包根目录执行；只复制本技能时，进入其父目录运行相同命令：

```text
python -B stream-perf-analysis/scripts/analyze.py stream-perf-analysis/examples/sensor-performance.jsonl --contract stream-perf-analysis/examples/sensor-contract.json
```

预期退出码 0，`valid_windows=1`，窗口 A 的 1→2。每阶段新增 10 个样本：

| 阶段 | 耗时差 us | 窗口均值 ms | 累计最大值 us |
| --- | --- | --- | --- |
| sample | 30000 | 3 | 7000 |
| pipeline | 100000 | 10 | 16000 |

`sample` 均值为 `(40000-10000)/(20-10)/1000=3ms`。`pipeline` 包含采样，不能将两者相加得到 13ms。两个累计最大值都比前报告增大，故7/16ms也是本窗口最大值。窗口n=10，若采用nearest-rank经验P95，第ceil(0.95×10)=10个值恰是最大值，得到7/16ms；线性插值P95仍不能确定。没有指定算法时不能声称给出了唯一的P95。缺少采集周期、排队及显示时间，也不能据此判定端到端瓶颈或 FPS。

## 重连与计数回退

```text
python -B stream-perf-analysis/scripts/analyze.py stream-perf-analysis/examples/sensor-boundaries.jsonl --contract stream-perf-analysis/examples/sensor-contract.json
```

预期退出码 0，5 个完整报告、2 个有效窗口：A 的 1→2 与 B 的 4→5。A2→B3 因连接变化断开，B3→B4 因计数回退断开。两段有效窗口均为 sample=3ms、pipeline=10ms；CLI 的 `last_window` 只显示 B 的 4→5。计数回退不能单独证明设备发生重启。

## 格式不匹配

`sensor-events.jsonl` 是接收事件，不是累计快照，也没有协议定义。不要改字段名拼成累计数据。可计算同一 epoch 内接收间隔 40/50ms；不能把它解释为曝光、完整帧率或端到端延迟。下一步应取得协议帧定义和采集时间依据。
