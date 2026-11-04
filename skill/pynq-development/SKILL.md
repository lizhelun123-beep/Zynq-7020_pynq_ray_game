---
name: pynq-development
description: 开发和调试 Linux/PYNQ 应用，覆盖环境确认、BIT/HWH、Overlay、自定义 IP、Python/C 接口及 DMA 交接；按任务加载示例，纯离线核对不初始化设备。
---

# Linux/PYNQ 开发

沿用目标项目的 Linux/PYNQ、Python 与原生 C/C++，交付完成当前任务所需的代码和验证结果。先从已有文件确定环境，缺少影响实现的信息再提问。本包的历史 Standalone 入口不作为当前默认路线。

## 选择路径

| 当前任务 | 按需读取或执行 | 本步产物 |
| --- | --- | --- |
| 新应用、迁移、Overlay 或自定义 IP | [PYNQ 开发流程](references/pynq-workflow.md) | 环境/制品/IP 接口与最小实现路径 |
| 离线检查 HWH | [文件检查器](scripts/inspect_hwh.py)，输入用户自己的 HWH | 声明的模块、VLNV、参数、地址窗口与文件指纹 |
| Python 调用已有 C/C++ | 流程中的原生接口小节、[数组包装示例](examples/native_array.py)、[C 库与 ctypes 模板](references/native-demo.md) | 明确 dtype/shape/stride/所有权、ABI 及错误传播的包装代码 |
| 从 HLS 或自定义 RTL 新建 Overlay | [PYNQ 加速器流程](../pynq-accelerator-flow/SKILL.md) | 按 IP 来源选择模板，分别验证工具准备、仿真、构建、DefaultIP 与中断 |
| 采集、显示、加速器 DMA | [DMA 契约](../pynq-dma-contract/SKILL.md)，按需看其完整离线示例 | 布局检查、具体交接与有界停机实现 |
| 功能已正确、需要定位慢在哪里 | [流式分析](../stream-perf-analysis/SKILL.md) | 同域测量与证据支持的优化建议 |
| IP/RTL 或构建制品确需变化 | [工具链路由](../xilinx-project-flow/SKILL.md)及相关验证门 | 当前授权范围内的硬件变更或同源制品核对 |

不要一次加载整包。先完成一条路径；遇到明确依赖再加载对应资料。

## 从输入到可验收结果

1. 核对实际板卡、镜像/内核、PYNQ/Python 版本、CPU ABI、驱动文件与 BIT/HWH 来源。可从工程说明和包元数据取值；不为查版本导入会初始化设备的模块。
2. 离线用文件解析核对 IP 参数、寄存器接口和构建身份。HWH 声明或同名文件不证明已下载、可访问或与 BIT 同代；`Overlay(download=False)` 不作为离线解析器。
3. 根据真实接口写当前任务的最小应用或修复。开发任务提供完整函数、调用方式、错误处理和验收输入；不要只列检查事项。保留既有 C 核心，不因使用 PYNQ 就重写算法。
4. 先用文件/替身验证代码契约，再在明确授权的板端范围核准驱动绑定、分配器/同步语义和实际结果。加载 Overlay、访问 MMIO、启动 DMA 与连接设备的授权分别沿用当前任务；离线示例不会赋予这些权限。
5. 给出实际命令、输出、已验证层次和剩余一个阻塞。Python 应用或已有 Overlay 的用户态改动通常不要求重新生成 BOOT、内核或 rootfs。

## 可直接复用

从技能包根目录执行：

```text
python -B pynq-development/scripts/inspect_hwh.py pynq-development/examples/synthetic.hwh --ip demo_dma
python -B pynq-development/examples/native_array.py
```

第一条仅使用标准库，读取合成 HWH，结果 `scope=OFFLINE_DECLARATIONS_ONLY`，窗口 span=65536。第二条需要已安装的 NumPy，仅用 Python 替身模拟 native，输出 `scope=MOCK_NATIVE_ONLY`。均不导入 PYNQ、不加载动态库或访问设备。

提示词：

```text
使用 $pynq-development。目标项目/任务：填写；现有镜像、PYNQ、BIT/HWH与代码入口：填写或提供证据路径。
先确认所需路径与实际版本，复用已有驱动和C核心，完成最小实现与正反例。
仅在本轮已授权范围操作板端；输出运行方法、实际验证和剩余缺项。
```

来源与版本依据见开发流程。最小输入与预期输出见[复用说明](../references/reuse-guide.md#pynq-development)，Overlay 与寄存器问题见[踩坑清单](../references/pitfalls.md#p01-overlay)。需要评估效果时读[验证记录](../references/validation-results.md)：跨题结果属于整体材料，不能单独归因给本技能；脚本/替身只证明离线契约，目标 ARM C ABI 和 PYNQ 实板移植仍需验证。
