# 部署与板测验收

先复用目标板现有镜像。记录实际板卡/器件、镜像、内核、PYNQ、Python、工具版本和构建身份；核准 PL、中断、时钟/复位的使用权。硬件命令必须属于当前授权范围；`--hardware` 或 Notebook 开关只是防误操作，不能替代授权。

## 主机与目标文件

1. 主机离线运行 `python -B scripts/run_board.py E:/pynq-work/bundle-001`，仅核对文件，不导入 PYNQ。源模板路径不能代替 binder 输出的 bundle。
2. 使用已有构建依赖可执行 `python -m pip wheel --no-deps --no-build-isolation assets/scalar-demo/python --wheel-dir E:/pynq-work/wheels-001`。这会生成 wheel，不应在未要求打包时自动执行。目标 Python/PYNQ 兼容性要单独核准；构建时不自动下载依赖。也可将该源码目录加入目标 PYTHONPATH，避免安装。
3. 经授权把 bundle、Python 包和本技能 CLI 或 Notebook 放入目标 Linux。需要安装时，使用已存在 wheel 和目标环境，`python3 -m pip install --no-deps --no-index ...whl`；不要装进主机环境或依赖联网拉包。本轮技能编辑不执行这些部署操作。

## 入口

Notebook 是 `assets/scalar-demo/notebooks/scalar_demo.ipynb`，默认关闭硬件开关。先填写目标 bundle 绝对路径，并按文件核准、独占权检查、加载、轮询、IRQ、关闭顺序执行。加载函数跨重复单元格保留所有者；unknown 状态不能通过重新运行加载单元格逃避恢复。

目标 CLI（在本技能目录）示例：

```text
python3 scripts/run_board.py /home/xilinx/bundle-001 --hardware --output /home/xilinx/evidence/poll-001.json
python3 scripts/run_board.py /home/xilinx/bundle-001 --hardware --irq --output /home/xilinx/evidence/irq-001.json
```

这两条命令会下载 PL 并实际运行，必须提前获授权。输出必须是新文件。首次板测只验证这个标量工程，不自动追加其他 DMA、服务、镜像或 SD 操作。失败时保留错误与所有权状态；不要自动重置全局 xlnk/CMA 或覆盖运行中的 Overlay。

## 分项验收

| 项目 | 通过证据 | 失败处理 |
| --- | --- | --- |
| 同源与运行环境 | 构建输入身份、真实报告、BIT/HWH/header 绑定、目标版本、读回寄存器 | 身份或布局不匹配即停止 |
| 轮询功能 | 零值、普通值、uint32 溢出向量与 CPU oracle 一致 | 保存输入/读回/错误，不修改期望 |
| 中断 | 同一批向量、真实 IRQ 通知计数、中断路由/驱动有效 | 不退化为轮询后仍宣称 IRQ 通过 |
| Notebook 复用 | 重复加载单元格返回同一 owner；并发提交拒绝 | 保留原 owner；不另建会话抢占 |
| 超时/取消 | 故障注入符合当前授权，unknown 禁止重入；确认 AP_IDLE 后恢复或按已审方案重载 | 未确认空闲不释放依赖资源 |
| 冷启动 | 操作者记录真实断电/上电动作、制品/环境/boot_id、启动后重新跑向量与 IRQ | 新 boot_id 只证明新内核启动，不证明断电 |

本 CLI 输出四个向量及环境，只覆盖相应入口；Notebook 复用、取消和物理冷启动需要额外真实操作证据，不由 CLI 的 PASS 一并证明。高带宽数据通路另测 DMA 所有权、缓存、行步幅、端到端延迟和吞吐，不能从这个标量示例外推。

依据：[PYNQ Python 包部署](https://pynq.readthedocs.io/en/v2.6.1/overlay_design_methodology/python_packaging.html)。
