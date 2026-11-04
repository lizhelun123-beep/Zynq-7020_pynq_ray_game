# PYNQ 启动

目标环境：AX7Z020B、PYNQ 2.6.2、Python 3.6.5、ARMv7 hard-float Linux、GLIBC 2.27。

将提交包的 `board/runtime/` 整体复制到板卡 `/home/xilinx/jupyter_notebooks/beam_v14/`，保留目录结构。使用已有 PYNQ 系统，不以裸板 BOOT 替换 Linux 启动文件。

在 SSH 终端进入该目录：

```sh
python3 -B beam_v14.py --inspect
python3 -B beam_v14.py --check
```

`--inspect` 检查文件；`--check` 读取系统和设备所有者。业务 UART `/dev/ttyPS0` 不能同时作为内核 console、getty 或串口终端。首次系统配置需核对实际启动文件并保留备份；已配置板卡不重复部署。

当前 boot 无有效受保护准入时，执行实际硬件准入，成功后启动：

```sh
sudo python3 -B beam_v14_ready_v2.pyz --qualify
sudo python3 -B beam_v14.py --run
```

`--qualify` 检查当前 boot、所有者和 PS 隔离，加载配对 Overlay 并读取实际设备状态。拒绝时保留输出，不手工修改回执或 boot UUID。已有有效同 boot 回执时直接 `--run`。

Ctrl+C 请求安全退出，确认 DMA 停机后再释放缓冲。Jupyter 入口为 `pynq_vision/notebooks/beam_v14_pynq.ipynb`，与命令行共用 Session，同时只运行一份。

电脑运行配套网页与权威 C 游戏会话，业务数据使用 UART v3/115200；SSH 用于管理。
