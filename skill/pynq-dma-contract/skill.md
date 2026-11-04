---
name: pynq-dma-contract
description: 开发和检查 Linux/PYNQ 的 DMA/VDMA 布局、cache 同步、缓冲所有权与安全退出；适用于采集、显示或加速器交接，附离线完整生命周期示例。
---

# DMA 布局与所有权契约

面向Linux/PYNQ应用的采集、显示与加速器交接。保留原技能名；历史Standalone记录只作为经验来源，具体API按当前PYNQ版本核准。离线示例不要求安装PYNQ。

开发时按需读 [完整行复制与停机示例](references/pynq-lifecycle.md)，交付可审查的代码、调用与失败路径。初建PYNQ应用先读 [开发入口](../pynq-development/SKILL.md)。

## 使用方法

先选择 capture、display 或加速器交接的一条实际路径。按需使用 [契约模板](references/contract-template.md)，只填与当前问题有关的字段。当前工程适配见 [工程上下文](../references/project-context.md)。

1. 核对实际格式、width/height、行有效字节、stride、span、地址范围、缓冲数和 cache 属性。同分辨率不等于同像素格式或步幅；不知道的项写 UNKNOWN。
2. 按每个槽画出 CPU/device 读写与复用顺序。说明提交、完成和退休的依据，保留序号与代次；禁止在设备仍持有时读写、复用或释放。
3. 分清 cache 同步与所有权：flush/invalidate 不能证明设备已完成。设备写完成 → 同步 → CPU 读；CPU 写 → 同步 → 设备读。内存屏障、缓存行和 DMA 实际访问 span 按平台 API 核对。
4. 按实际DMA/VDMA类型与驱动核准停机和未完成访问的语义，再决定相关槽何时可释放。仅有stop请求、计数安静、PARK变化或无CRC错误不能代替退休/排空证据。无法确认时保留所有权。
5. 先做布局算术或 host 反例；需要真实单块传输时沿当前任务授权执行。不因为使用技能就连接设备或下载 Overlay。

## 可执行静态检查

从技能包根目录（本仓库为 `大赛文档/skill/.skill/`）运行：

```text
python -B pynq-dma-contract/scripts/check_layout.py pynq-dma-contract/examples/layout.json
python -B -m unittest discover -s pynq-dma-contract/scripts -p test_check_layout.py
python -B pynq-dma-contract/examples/lifecycle.py
```

输入格式见 [布局格式与限制](references/layout-schema.md)。例子是合成的 BGR24 三槽布局，不是板卡地址。预期 CLI 退出 0，`status=PASS_STATIC_DESCRIPTION`，`buffers=3`。脚本检查完整 stride 行分配、64 位范围、cache 行对齐、槽间重叠及声明的 CPU/device 访问冲突。它不读取寄存器，也不能验证实际退休栅栏、cache API、总线完成或 HALTED。

## 可复制提示词

```text
使用 $pynq-dma-contract。目标平台/运行环境：填写板卡、OS 或 Standalone。
输入：通道格式、stride/span、实际分配范围、缓存属性、提交/完成/退出代码。
本次问题：填写出现撕裂、旧帧、越界、超时或释放风险的具体条件。
先沿一个槽列出所有权变化和完成证据，再给最小修复；缺失证据保持 UNKNOWN。
先做离线检查，硬件验证仅在本次已有授权范围内执行。
```

## 失效条件与迁移边界

物理/设备地址来源不明、scatter-gather/共享别名未建模、cache 一致性未知、完成与退出依据缺失时不能通过。附带布局器只支持互不重叠的独立线性缓冲；共享同一物理内存的别名和 SG 描述符需另作明确建模，不能靠改地址绕过检查。

## 经验来源与效果

原工程将 PARK/当前指针当作完成的推断改为明确退休证据，保留两个新 START 后才能租借旧槽的机制；退出须确认 HALTED，计数 quiet 不作排空证明。已有 DMA/首错反例覆盖 719 行与 CRC0 不一致等情形，属于历史 host 模型结果，不是本轮新实板证明。相关原文见 [project-evidence.json](../references/project-evidence.json) 的 `safety`、`validation`。本轮新增的布局脚本可在任意 Python 3.8+ 主机运行，正反例只证明静态描述检查。

最小输入与输出见[复用说明](../references/reuse-guide.md#pynq-dma-contract)。错误、HALTED 与可重新提交分别判定；恢复失败后保留缓冲不等于提前释放，具体触发与调查见[DMA 踩坑](../references/pitfalls.md#p04-dma)。本包生命周期是离线替身，不是已验证的真实 PYNQ DMA 适配器。整体模型对照与恢复判据分歧见[验证记录](../references/validation-results.md#cross-task-experiment)。
