# 最小 PYNQ 工程路径

本技能补充可修改的工程模板，默认保留现有 Linux/PYNQ 镜像。模板计算 `uint32(x+bias)`，用于打通接口与部署，不用于证明加速收益。代码由本包编写；工具命令参考 AMD/PYNQ 官方资料，未从其他板卡复制 DDR/MIO 或管脚配置。

## 输入与分阶段运行

下列命令均在本技能目录执行。主机 Python 3.8+；目标 Python 包使用 Python 3.6+ 语法。HLS/Vivado 脚本以 2023.1 接口为基线，实际版本必须写入 profile；其他版本需要核准入口和命令。不能仅修改版本字符串就宣称兼容 2025.2/2026.1。

1. 复制 `assets/scalar-demo/profile.example.json` 到工作目录。填写真实 `board_label`、`xc7z...` 器件和完整工具版本；`clock_mhz` 是请求值，需核准实际时钟。`ps_preset_tcl` 指向已审查的同板 PS7 DDR/MIO 预设，路径相对 profile。该 Tcl 通过变量 `$ps` 访问处理器单元；内容需来自实际工程/板卡资料，不能照抄 Z1/Z2。准备脚本只校验文件身份，不执行预设。
2. 选择尚不存在的输出目录，执行准备。profile 与模板哈希记录在 `inputs.json`；源文件发生变化要开新构建，不能沿用阶段标记。

```powershell
python -B scripts/validate_template.py
python -B scripts/prepare.py E:/pynq-work/profile.json --output E:/pynq-work/build-001
$env:PYNQ_DEMO_CONFIG='E:/pynq-work/build-001/config.tcl'
$env:PYNQ_DEMO_STAGE='prepare'
vitis_hls -f assets/scalar-demo/hls/build_hls.tcl
```

`prepare.py` 只准备文件。上述 HLS 命令会启动真实工具；执行前需已有相应授权。记录 `vitis_hls` 的真实版本。2026.x 若无此启动器，应按对应 AMD 文档适配 `vitis-run`，本包没有验证该替代入口。HLS 的 `flow_target vivado`、IP VLNV 和寄存器布局是配套契约。

3. 后续每条单独设置 `PYNQ_DEMO_STAGE` 再运行同一 HLS 命令：`csim` → `synth` → `ip`。`ip` 仅导出 IP catalog，不隐含 Vivado 实现。C 仿真、综合报告、导出头文件各自保存；C 仿真通过不能代替 RTL 协议验证。
4. 切换 Vivado 入口，依次为 `prepare` → `synth` → `impl`。每次设置阶段后执行：

```powershell
vivado -mode batch -source assets/scalar-demo/vivado/build_bd.tcl
```

BD 使用 PS7 GP0、标量 AXI-Lite IP、AXI INTC 和复位模块；没有 DMA、HP 数据口或用户管脚。外部 DDR/FIXED_IO 的实现约束仍依赖正确的同板 PS 预设。HLS 中断接 INTC，再接 PS；不能省略路由后仍声明中断支持。`prepare` 会校验 BD，但只有真实工具运行才能发现 IP/属性/地址/约束问题。

5. `impl` 停在 route_design，生成 timing/cdc/drc/utilization/clocks 报告。按实际顶层审查约束、复位/CDC、无约束路径、WNS/TNS/WHS/THS 和资源预算。生成审查草稿：

```powershell
python -B scripts/gate.py --receipt E:/pynq-work/build-001/inputs.json
```

将输出保存为新 gate.json，逐项根据真实报告填写指标、报告 SHA256 和审查者。草稿默认 NOT_RUN；未知值、负时序、未审查资源、未解决 Critical CDC/DRC 均拒绝。该脚本核验**审查声明及报告身份**，不解析报告、不代替工程既有验收器，也不能靠填写 PASS 形成时序证据。所有阶段标记只是执行记录，不能防止人为替换工程输出。

6. 只有实现审查通过且导出获授权，才设置 `PYNQ_DEMO_STAGE=export`、`PYNQ_DEMO_GATE_RECORD` 为 gate.json 绝对路径，再调用 Vivado。该阶段生成 BIT 与包含比特流的 XSA。按实际导出位置取生成的 `xadd_bias_hw.h`，不能手写头文件替代真实 HLS 结果：

```powershell
python -B scripts/bind_artifacts.py --xsa E:/pynq-work/build-001/export/scalar.xsa --header E:/pynq-work/build-001/hls/solution/impl/ip/drivers/add_bias_v1_0/src/xadd_bias_hw.h --receipt E:/pynq-work/build-001/inputs.json --gate E:/pynq-work/build-001/gate.json --output E:/pynq-work/bundle-001
```

工具目录可能随版本变化，先确认实际文件。绑定器要求 XSA 中唯一 BIT/HWH、匹配本模板 VLNV/寄存器字段及原输入身份。它输出 scalar.bit/hwh、头文件、声明和哈希清单；这些证明检查时的文件绑定，不能单独证明硬件行为、源文件真实性或冷启动。

## 当前证据边界

本包提供离线正反例、Notebook 语法检查和 Tcl 完整性检查。Tcl `info complete` 仅检查词法/括号完整性。HLS C 仿真、真实工具 prepare、RTL/综合/实现、目标包安装、中断、板测和冷启动必须实际执行后再记录通过；初始均为 NOT_RUN。不要把合成的测试 HWH、gate 或 BIT 用于目标板。

官方依据：[PYNQ 2.6.1 Overlay 教程](https://pynq.readthedocs.io/en/v2.6.1/overlay_design_methodology/overlay_tutorial.html)、[AMD 2023.1 HLS IP 导出配置](https://docs.amd.com/r/2023.1-English/ug1399-vitis-hls/config_export)、[AXI-Lite 控制寄存器](https://docs.amd.com/r/2023.1-English/ug1399-vitis-hls/S_AXILITE-Control-Register-Map)。
