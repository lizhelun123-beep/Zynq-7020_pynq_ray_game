---
name: pynq-accelerator-flow
description: 从 HLS 或自定义 RTL IP、Vivado BD 到 PYNQ 驱动、中断及分阶段验收的最小工程模板。
---
# PYNQ 加速器闭环

用于新建可复用 Overlay；已有应用问题直接选专项技能。默认复用现有镜像。

1. 先确定 IP 来源：HLS 只读[HLS 路径](references/walkthrough.md)；自定义 RTL 只读[RTL 路径](references/rtl-flow.md)。核准实际板卡、PS 预设和工具版本，不把两套寄存器 ABI 混用。
2. 用[模板检查器](scripts/validate_template.py)做离线检查。实际工具准备、功能仿真、综合、实现、导出分别过门；每次只运行已授权阶段，失败保留证据，未运行阶段为 NOT_RUN。
3. 按[寄存器契约](references/register-contract.md)核对 START 快照、清除语义、超时和所有权。只有中断任务才加载对应驱动/中断参考；不把全部参考文件预先塞入模型上下文。
4. HLS 用[制品绑定](scripts/bind_artifacts.py)；RTL 用[分阶段入口](scripts/run_rtl.py)绑定同源 BIT/HWH/XSA。只在已授权目标板上加载；真实 IRQ、恢复和冷启动须另行板测。[新板/镜像分支](references/board-porting.md)仅在需要时启用。

从本技能目录运行 `python -B scripts/validate_template.py`。HLS 模板在 `assets/scalar-demo/`，RTL 模板在 `assets/rtl-demo/`。不自动安装依赖、编译硬件或连接板卡；两个路径各自声明验证范围。

最小输入与输出见[复用说明](../references/reuse-guide.md#pynq-accelerator-flow)。封装、BRAM 与报告问题按需查[踩坑清单](../references/pitfalls.md#p03-packaging)。需要判断完成范围时读[验证记录](../references/validation-results.md#package-scope)，区分模板本体与跨题候选工程。
