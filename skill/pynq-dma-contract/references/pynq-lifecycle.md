# Linux/PYNQ 行复制与停机示例

[lifecycle.py](../examples/lifecycle.py) 是完整的离线替身例子。包根目录运行：

```text
python -B pynq-dma-contract/examples/lifecycle.py
```

预期 `scope=MOCK_LIFECYCLE_ONLY`、`rows=3`、事件顺序 `flush,start,request_stop`，最后 `owner=released`。代码只操作bytearray，不分配CMA，不导入PYNQ，不释放真实设备缓冲。

## 实现和迁移

- 物理布局先用现有 `check_layout.py` 检查。当前API的Slot只有CPU字节数组和应用状态，不建模物理地址别名；真实槽必须已证明与活动槽不重叠。不能仅凭“B未提交”忽略B与活动A的重叠。
- `copy_rows` 显式接收source_stride和目标stride，逐行只复制有效字节并保留目标padding；源接口限一维连续字节缓冲。任意NumPy切片/负stride必须先按真实数组索引或Python/C接口规则整理，不假定源行步长恒为width×BPP。
- `flush` 的替身只演示调用顺序。真实缓存同步必须按实际PYNQ Buffer/分配器语义核准；普通NumPy的地址不是设备地址。
- `submit` 在start之前移交所有权。即使start抛异常，也保守保留device状态，避免“命令失败”但设备已开始读取时回收内存。
- `release_after_stop` 完整给出单调期限、停止请求、结构化状态轮询和异常/超时后的保留策略，没有隐藏的等待帮助函数或无条件finally释放。状态同时满足halted且非running才释放替身；真实适配器还须证明该状态意味着设备不再访问此槽。

## 明确的替身接口

`read_status()` 返回 `{running: bool, halted: bool, error: bool}`，`request_stop()` 只发停止请求。这两个**替身**调用均保证及时返回，外层期限才有意义；错误状态不是停机确认。异常沿函数向上传播，slot仍由设备持有。

真实PYNQ API没有自动满足这一接口。PYNQ2.6.1的simple DMA `stop()` 中有等待循环，不能直接把它当作本例非阻塞request_stop；外层加单调期限或线程超时也不能证明内部调用已终止。先核准目标驱动、停止/复位与HP访问语义，再实现专用适配器；未确认之前保留缓冲和所有者。依据见 [PYNQ开发流程](../../pynq-development/references/pynq-workflow.md)。

本例验证的是CPU复制、应用状态和失败处理契约。PARK切换、VDMA退休、SG、中断、真实cache和设备排空都需目标项目自己的证据。
