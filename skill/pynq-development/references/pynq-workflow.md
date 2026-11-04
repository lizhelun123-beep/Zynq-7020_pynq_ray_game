# PYNQ 开发流程与版本检查点

## 先确定环境

记录实际板卡/器件、镜像/内核、Python/PYNQ 版本、当前 PL 使用者、驱动来源、BIT/HWH 构建身份和验收目标。复用工程已有记录；版本可从安装包元数据查，不靠导入 PYNQ 或加载分配器来获取。目录名 baremetal、某块 PYNQ 示例板、HWH 的时钟请求都不能替代实际运行证据。

本包默认服务 Linux/PYNQ 开发；Standalone/FSBL/BOOT 仅在明确启动交付任务中使用。纯 Python 改动先验证应用；原生 C 改动核准目标 ABI、加载器/glibc 与编译器；仅确需新增/修改 IP 时再进入 Vivado/HLS。

PC离线检查工具的Python3.8+要求不等于板端镜像的Python版本；板端代码须匹配实际环境。已有驱动、分配器与显示缓冲机制优先复用，不因参考文档换用另一套后端。

## BIT/HWH → Overlay → IP

1. 取得当前制品的构建记录和真实 HWH。离线运行 `inspect_hwh.py`，检查目标 FULLNAME、VLNV、参数和声明的地址窗口。检查器仅提取 UTF-8、无命名空间 SYSTEM/MODULE/MEMRANGE 的常见声明，不重建 PYNQ 的 ip_dict、时钟、GPIO或中断拓扑；多窗口保留全部，不猜哪个是 PS 可达 MMIO。
2. 将寄存器偏移、位宽、端序、控制/完成语义与实际 IP 文档、HDL/HLS 接口和生成头文件对照。没有接口证据时继续补文件，不能默认 ap_start/ap_done 的偏移和位定义。
3. 在获准板端编程且已处理当前使用者/恢复方式后，使用实际匹配版本加载 Overlay。随后对比 `ip_dict` 与离线声明，确认绑定的驱动类型；不为了消除警告默认 `ignore_version=True`。
4. 优先复用实际驱动；确需新增`DefaultIP`/自定义驱动时，按已确认的VLNV和寄存器契约编写。构造函数可能触及设备；板端诊断先选一个已知输入和可核对结果，不运行未知副作用的寄存器读写。

以下是**获准目标板编程后的操作片段**，不是本机离线命令；bitfile 和 ip_name 必须来自已核准输入：

```python
from pynq import Overlay

overlay = Overlay(bitfile)
description = overlay.ip_dict[ip_name]
print(description["type"], description["phys_addr"], description["addr_range"])
```

文件同名或指纹相同只证明相应文件事实，不能单独证明同次构建、驱动兼容或当前 PL 已加载。纯离线不执行此片段。

## Python/C 用户态接口

需要真实 C 源码和 ctypes 绑定时使用 [C 库与数组模板](native-demo.md)，包含显式 ABI、长度/stride、错误码与编译入口；`native_array.py` 的 callable 替身与真实 C 编译/加载分别验证。没有编译器时明确 NOT_RUN，不自动安装。

先保留已有 C/C++ 核心，明确输入输出 shape、dtype、连续性/stride、端序、缓冲所有权、错误码与调用次数。NumPy 普通地址可以作为已核准 CPU ABI 的参数，但不能冒充 DMA 设备地址。

[native_array.py](../examples/native_array.py) 展示完整包装：验证 uint8 H×W×3；非连续/负stride源按需复制；只读源不改写；独立C连续输出；非零状态抛异常，native异常原样传播。该 callable 契约需由真实绑定层实现，示例不会加载 C 动态库。数组代码按需依赖 NumPy；未安装时只跳过相应可选验证，不自动安装。

绑定已有库前，核准目标 ARM ABI、符号、参数长度/stride、动态加载器及依赖；未知库的构造/析构也可能访问设备，不能用加载库代替静态检查。本机 Python 替身通过后，再分别确认真实库和板端已知输入，不能转签 ABI 或设备完成。

## DMA/VDMA 应用

先区分 AXI DMA simple/SG、VDMA、CDMA；按实际驱动核准分配地址、长度、DRE/对齐、flush/invalidate 与完成/停止语义。先运行已有 [布局检查](../../pynq-dma-contract/SKILL.md)，再读其有界停机与行复制示例。替身接口明确返回结构与调用有界性，不能直接把可能阻塞的 PYNQ stop/wait 绑定为非阻塞适配器。

设备写完成与CPU同步后才能读取；CPU写入同步后才移交设备；退休证据或语义匹配的停机确认后才复用/释放。显示切换还需证明旧槽退休，不能只看PARK。任何异常都保留无法确认已退休槽的所有权。

## 版本依据与参考适配

新建 HLS/BD 工程可按 [PYNQ 加速器流程](../../pynq-accelerator-flow/SKILL.md)选用配套模板。该分支需要真实 PS7 预设和工具版本；工具准备、构建、目标驱动/IRQ 与冷启动分别验收，不由离线语法检查代替。

以下是核对过的 **PYNQ 2.6.1** 文档/源码入口，不代表所有2.6或3.x环境实现相同：

- [allocate / Buffer](https://pynq.readthedocs.io/en/v2.6.1/pynq_libraries/allocate.html)：设备缓冲、device_address、coherent与同步方法；移植时核准实际分配器实现。
- [DMA模块源码](https://pynq.readthedocs.io/en/v2.6.1/_modules/pynq/lib/dma.html)：simple DMA的wait无timeout参数，start/stop含轮询；驱动构造也会启动通道。外层期限不能给内部阻塞调用凭空增加硬超时。
- [Overlay模块源码](https://pynq.readthedocs.io/en/v2.6.1/_modules/pynq/overlay.html)：构造涉及设备元数据/驱动，download涉及时钟与硬件；download=False不是通用无副作用承诺。
- [HWH解析源码](https://pynq.readthedocs.io/en/v2.6.1/_modules/pynq/pl_server/hwh_parser.html)：模块、VLNV、参数与MEMRANGE字段参考；本包检查器独立编写，只做较小范围的文件提取。

结构借鉴 xilinx-suite 的阶段路由、先确认版本再实现、交付命令与预期输出；未搬入其MPSoC默认配置、PetaLinux重建或外部实现代码。旧版工程入口仅作历史适配，当前项目决定以本轮任务和PROJECT_STATE.md为准。
