# 驱动、事件和所有权

配套 Python 源码在 `assets/scalar-demo/python/pynq_scalar_demo/`。基础模块不导入 PYNQ；只有 `board.py` 导入 DefaultIP/Overlay。驱动 `bindto` 绑定 `example.org:hls:add_bias:1.0`，构造前检查 HWH 派生的地址范围。寄存器偏移只用于这个模板：CTRL/GIE/IER/ISR 为 0/4/8/12，x/bias/y 为 0x10/0x18/0x20。真实 HLS 头文件和 HWH 必须匹配；不匹配时停止，先审接口，不能关闭检查绕过。

同步调用 `ip.add(x, bias, timeout)` 验证 uint32 和有限正超时，确认 AP_IDLE，再启动并轮询 AP_DONE。每个会话只允许一个调用。启动写可能部分成功，任何不确定异常将状态转为 unknown；不能当成未启动重新提交。外层超时无法限制卡死的 MMIO read，因而不承诺整个进程一定在指定时间内返回。

异步调用 `await ip.add_async(...)` 先启用 IP 中断并注册 `Interrupt.wait()`，让出一次事件循环后再写 AP_START；即使 IP 一周期完成，也必须收到一次真实 IRQ 唤醒才返回。等待通知后读取 pending ISR 并写回相同位：这里的 ISR 是 toggle-on-write，不能无条件写 1，也不能套 W1C 操作。随后检查 AP_DONE、读取输出、屏蔽 IP 中断。虚假通知继续等待，按同一截止时间计算。

PYNQ 2.6.1 的 Interrupt 取消路径可能保留 `waiting` 标记或控制器登记。超时/取消后，本会话禁止复用异步 IRQ；不要访问私有控制器或把 `waiting=False` 当成修复。先保留所有者，确认这个**无 DMA、无内存主机**的标量 IP AP_IDLE，调用 `recover_if_idle()` 清理 IP 侧状态；此后可恢复轮询，异步仍需安全关闭后重建 Overlay/中断对象。重下载也必须重新取得所依赖 PL 的独占权。AP_IDLE 不能证明 AXI DMA/VDMA、HP 写事务或其他 IP 已排空。

Notebook 使用顶层 `await`，不在已运行事件循环中调用 `asyncio.run()` / `run_until_complete()`。命令行使用自己的事件循环。`open_board()` 保留模块级唯一所有者，同一路径与 manifest 身份重复调用返回同一会话；切换制品前先关闭旧会话。不要由其他代码下载 Overlay 或手工修改寄存器；发生外部重配置后此所有权假设失效，必须停止并重新核准。

验收应覆盖：实际 IRQ 通知计数、重复单元格不二次下载、无 IRQ 超时、任务取消、未知状态拒绝重入、确认空闲后轮询恢复、关闭幂等。离线 fake 只能验证状态机，不证明 Linux UIO/设备树或实际中断路由。

依据：[PYNQ Interrupt](https://pynq.readthedocs.io/en/v2.6.1/pynq_libraries/interrupt.html)、[Interrupt 源码](https://pynq.readthedocs.io/en/v2.6.1/_modules/pynq/interrupt.html)、[PYNQ 与 asyncio](https://pynq.readthedocs.io/en/v2.6.1/overlay_design_methodology/pynq_and_asyncio.html)。换版本需重查取消和清除语义。
