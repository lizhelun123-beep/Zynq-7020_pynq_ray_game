# C 库、ctypes 与 NumPy ROI

[C 头文件](../examples/native/bgr_reverse.h)和[实现](../examples/native/bgr_reverse.c)提供 CPU BGR→RGB 示例，显式长度、stride 与尺寸；拒绝短缓冲、溢出和输入输出重叠，仅写活动像素，保留行 padding。此函数无设备访问，不接收物理/DMA 地址。

有现成 GCC/Clang 时，从本技能目录执行：

```text
python -B scripts/build_native.py --output E:/pynq-work/native-host-001
python -B -m unittest discover -s scripts -p test_native_library.py
```

构建入口不安装编译器，目录必须尚不存在。主机 DLL/SO 只用于主机测试。目标板可用已核准的原生 GCC，或明确匹配目标 sysroot 的交叉编译器，例如 ARMv7 hard-float 的 `arm-linux-gnueabihf-gcc -std=c99 -O2 -fPIC -shared examples/native/bgr_reverse.c -o libbgr_reverse.so`；实际架构/端序/浮点 ABI/动态加载器/glibc 依赖必须从目标确认，不直接套用这个示例命令。

仅在已审查的库路径上构造 [NativeBgr](../examples/native_binding.py)；CDLL 构造本身可能执行库初始化。绑定固定 argtypes/restype，先检查 ABI 版本。同步调用持有输入与输出引用；不用于异步存储指针、回调或可重入性未知的库。

```python
from native_array import convert
from native_binding import NativeBgr
native = NativeBgr('/home/xilinx/lib/libbgr_reverse.so')
rgb = convert(image[:, 1::2, :], native)
```

[数组适配](../examples/native_array.py)将只读/带步幅/负步幅 ROI 转为连续输入，独立分配输出，不改写原图。`convert()` 的 native-callable mock 测试不证明 ctypes/C ABI；`test_native_library.py` 才编译并加载真实库。缺 NumPy 或编译器时明确跳过相关测试，不自动安装，也不将跳过记成通过。

目标验收：用已知颜色与 ROI 检查结果，记录目标编译/依赖/库哈希；在实际已同步的 CPU 可读输入上测复制、绑定、算法各段时间。主机可加载、mock 正确和函数返回 0 都不能证明板端兼容、DMA 同步或性能提升。
