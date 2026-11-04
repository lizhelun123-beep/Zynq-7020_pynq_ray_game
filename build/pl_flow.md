# PL 构建与硬件身份

工具：Vivado 2023.1；器件：xc7z020clg400-2。构建入口为 `run_pl.py` 与 `build_pl.tcl`。

## 新Overlay与同源报告

已按用户授权从 `pr4` 报告使用的原始布线检查点直接导出新Overlay，实际成功导出目录为 `tmp/px2`。
没有重做综合/布局布线，没有修改输入窗口、tap或路由。
新文件位于 [overlay_candidate/](overlay_candidate/)，三个文件保持同一 `system_wrapper` 文件名。
该目录与仍被冻结的 `board/runtime/` 是两份不同的硬件载荷，不能混用它们的身份或验收结果。

| 新Overlay文件 | SHA256 |
| --- | --- |
| [system_wrapper.bit](overlay_candidate/system_wrapper.bit) | `408adfdc3b2ebf00f2dec25e6a90f140e188b122ffe894aa7aad5fb08b1256fc` |
| [system_wrapper.hwh](overlay_candidate/system_wrapper.hwh) | `fa121904ae7f1c32c9b42244b74cfe7366aff3370760d1c88f5286a9693715df` |
| [system_wrapper.xsa](overlay_candidate/system_wrapper.xsa) | `4c25bbe4995b6d423bf4249de4f93a844c2c505a2fe205c3ffbfc2f96226b87a` |

[binding.json](overlay_candidate/binding.json) 是交付路径索引及哈希关系；原始导出记录保存在 `evidence/binding.json`。
对应关系已核对：提交源码144项输入清单 → `pr4` 综合/布线 → 完全相同字节的 routed DCP → 同次资源/时序报告 → 本次原生导出。
导出前重新读取该DCP，时序汇总的全部12项数字与原实现报告完全一致：setup +0.135ns、hold +0.052ns、脉宽+0.264ns，失败端点0。
XSA内BIT/HWH与交付文件逐字节一致；HWH也与该DCP内嵌HWDEF中的HWH逐字节一致。

Vivado在 `write_hw_platform -include_bit` 内再次执行bitgen，产生不同的BIT头部时间。
首次 `px1` 的独立BIT与XSA成员只差2个时间字节，完整1845788字节配置内容一致；严格校验原样拒绝了那次配套。
脚本随后修正为：先验证设计名/器件及完整配置内容一致，再从本次XSA原样提取BIT/HWH作为交付文件，保留较早BIT。
没有改写XSA、修改BIT时间字段或放过配置内容差异。`px1`原始失败和旧脚本保留在证据目录。
复现时文件头/ZIP时间可能变化，不承诺容器文件哈希跨运行相同；每次均重新核对本次配套关系与配置内容。

静态核对中地址映射、外部端口方向/宽度、PS和VDMA参数与旧运行硬件一致。
CSI元数据包含版本字段1→2、AXI-Lite地址宽4→5、debug关闭，D-PHY新增shared-enable等差异，详见 `evidence/interface_comparison.json`。

原始CDC/DRC/methodology告警仍需审阅。

可从包内保留的报告/DCP直接复现导出，无需原工作区的 `tmp/pr4`：

```powershell
$repo = 'D:/Workspace/AMD_camera/FPGA-main/FPGA-main'
$pkg = "$repo/output/submission/pynq_web_v14"
python -B "$pkg/build/export_overlay.py" `
  --from-build "$pkg/build/reports/sampling_window_build" `
  --output "$repo/tmp/px3" `
  --vivado-home 'D:/Xilinx/Vivado/2023.1'
```

`tmp/px3`必须全新，命令仅导出离线候选，不连接或加载板卡。现有 `px2` 已经完成，不需要为获得当前交付文件再运行一次。
6项新增负向/配套检查通过，覆盖拒绝失败时序、被改清单、地址映射、VDMA参数和真实配置差异；时间头差异按上述规则保留。

## 2026-11-03 接收路径修正与时序检查

本节是当前源码候选的最新结果；下文 `pr1/pr2` 与固定布线重分析保留为历史失败证据。

原接收路径为 IBUFDS → 时钟 IDELAY（0 tap）→ BUFIO/BUFR，数据为 IBUFDS → IDELAY（12 tap）→ ISERDESE2。
实际 `pr2` 路径显示，0 tap 的时钟 IDELAY 仍有插入延迟；Fast/Slow 下不同的时钟与数据延迟限制了共同采样窗口。
已有 DCP 的定向 ECO 结果保存在 `eco_probe/sampling_probe.tsv`：

| 定向模型 | 数据 tap | 最差 setup | 最差 hold |
| --- | --- | --- | --- |
| 原时钟路径、原15%～85%窗口 | 12 | +0.021ns | −0.844ns |
| 原时钟路径、原15%～85%窗口 | 24 | −1.029ns | −0.023ns |
| 旁路0-tap时钟IDELAY、原窗口 | 12 | −0.222ns | −0.156ns |

因此不能把增加数据 tap 当成同时满足两个角点的修正。本次只修改提交包中 `hs_clocking.vhd`：
请求0 tap时直接连接 IBUFDS 到既有 BUFIO/BUFR；请求正延迟时仍保留 IDELAY。
没有更换 PLL、分频器、数据 tap、字节对齐、相机表、运行软件或游戏配置。工作区另一份历史PL源码未被覆盖。

本次分析的25%～75%UI转换包络记录于 [camera_input_contract.json](camera_input_contract.json)。
名义HS仍为140MHz，lane280Mb/s、byte35MHz；UI=25/7ns。
输入min/max从0.535/3.036ns改为0.892/2.679ns，按1ps网格向保守方向取整，P/N和两个DDR参考边沿一致。

`tmp/pr3`受限运行在综合前因工具相对Tcl读取失败停止，文件实际存在且可读；失败记录保留。
同源输入在仅提升该构建命令执行权限的 `tmp/pr4` 中完成综合、布局布线和同次报告。
该对照支持执行环境影响，不把它当成已经证明的Vivado底层根因。

| 本次 `pr4` 实现后指标 | 实际结果 |
| --- | --- |
| setup WNS / TNS / 失败端点 | 0.135ns / 0.000ns / 0 |
| hold WHS / THS / 失败端点 | 0.052ns / 0.000ns / 0 |
| 脉宽 WPWS / TPWS / 失败端点 | 0.264ns / 0.000ns / 0 |
| 脚本状态 | REPORTS_COMPLETE；timing=PASS |

资源仍为LUT7485/53200、FF10738/106400、BRAM15/140、DSP0/220。
同一DCP的15448个可布线网络全部布通，路由错误为0；6项总线偏斜约束均通过，最差裕量+6.183ns。

在同一个新布线DCP上另做反事实检查，数据tap和位置均不改动。每种模型覆盖两lane、P/N、Fast/Slow、
数据rise/fall及setup/hold共32组查询：

| 同一新布线路径的输入包络 | MIPI最差setup | MIPI最差hold | 结果 |
| --- | --- | --- | --- |
| 声明25%～75%UI | 0.135ns | 0.201ns | 在声明包络下通过 |
| 历史15%～85%UI | -0.222ns | -0.156ns | FAIL |

`report_cdc/report_drc/report_methodology`的原始告警一并保留，时序PASS不替代这些项目的审阅。

同次报告、综合/布线检查点、有效约束、原始输入/暂存摘要、执行脚本及检查日志见
[reports/sampling_window_build/](reports/sampling_window_build/)。
`sampling_analysis/`保留两种窗口的64组查询及完整路径。
`previous_source_delta/`保留被改动的4份旧PL输入和旧构建入口，可与旧输入清单核对历史来源。
`build.json`同时记录约束文件哈希；23项主机检查通过不代替原生Vivado结果。
该报告阶段没有导出BIT/HWH/XSA；后续按用户授权完成的同源Overlay导出见本文最新结果。

窗口检查可用随包 [check_sampling_window.tcl](check_sampling_window.tcl) 对新候选DCP执行，参数是DCP与全新输出目录。
旧 [check_camera_timing.tcl](check_camera_timing.tcl) 仅用于保留的、含时钟IDELAY的旧DCP。

复核已归档的新DCP及两个窗口，无需重做综合和布局布线：

```powershell
$repo = 'D:/Workspace/AMD_camera/FPGA-main/FPGA-main'
$pkg = "$repo/output/submission/pynq_web_v14"
$env:XILINX_VIVADO = 'D:/Xilinx/Vivado/2023.1'
& "$pkg/build/vivado_nocd.bat" -mode batch -notrace `
  -log "$repo/tmp/sw2.log" -journal "$repo/tmp/sw2.jou" `
  -source "$pkg/build/check_sampling_window.tcl" `
  -tclargs "$pkg/build/reports/sampling_window_build/checkpoints/routed.dcp" "$repo/tmp/sw2"
```

`tmp/sw2`及日志名称须全新。

## 原运行Overlay与历史报告

`--inspect-only` 读取交付 BIT/HWH/XSA 和原始报告，输出硬件身份与报告对应关系。

| 对象 | 核对结果 |
| --- | --- |
| 交付 Overlay | BIT 头记录 2026-10-04 20:56:34，SHA256 为 `a5a88800af559c2e95ad67453deab7d4ec5bdfeaa3eccddc7279f0f2f64f3e55`。 |
| XSA 与运行文件 | XSA 内 BIT/HWH 与 `board/runtime/` 对应文件逐字节一致。 |
| 历史综合、实现报告 | `reports/raw/` 生成于2026-10-13。历史实现 WNS=-0.247ns、WHS=-1.111ns，时序未通过。 |
| 恢复的源码候选 | 已从 Git `b206663` 恢复完整 CSI 1.2 的51份文件，而非修改版本字符串。BD/IP版本和所有 IP 文件引用的精确大小写检查通过。 |
| XPR 输入 | 两份找回的其他构建导出 XDC 现已在 XPR 中停用并保留为历史文件，避免覆盖最终相机模型和本次生成的 IP/XPM 约束。AutoDCP 保留原引用。Tcl 直接打开隔离副本中的 XPR。 |
| 本轮电脑结果 | 用户 `tmp/pl2` 已实际完成综合和布局布线，但混用的相机模型下 hold=-1.111ns；随后完成下文的最终名义模型固定布线重分析，hold仍未通过。 |
| 校正源码的实际重建 | `tmp/pr1` 已完成综合、布局布线及全部报告，退出码0、`REPORTS_COMPLETE`、`timing_status=FAIL`；setup+0.021ns、hold−0.844ns。原始报告和输入摘要见下文。 |

## 执行命令

报告复现使用 `--reports-only`：完成综合、布局布线、报告和检查点，单独记录时序PASS/FAIL，始终不导出BIT/XSA。输出目录必须全新；已保留 `tmp/pl1`、`tmp/pl2`、`tmp/pl3` 和实际准备验证 `tmp/pv4`。当前报告构建目录为 `tmp/pr4`，下例使用新的 `tmp/pr5`。这个仓库位置下暂存工程路径为77字符，符合脚本的80字符上限。

```powershell
$repo = 'D:/Workspace/AMD_camera/FPGA-main/FPGA-main'
$pkg = "$repo/output/submission/pynq_web_v14"
python -B "$pkg/build/run_pl.py" `
  --project "$pkg/src/project" `
  --reports-only --output "$repo/tmp/pr5" `
  --vivado-home 'D:/Xilinx/Vivado/2023.1'
```

若只检查工程准备流程，可在新目录执行：

```powershell
python -B "$pkg/build/run_pl.py" `
  --project "$pkg/src/project" `
  --validate-only --output "$repo/tmp/pv5" `
  --vivado-home 'D:/Xilinx/Vivado/2023.1'
```

`--validate-only` 实际启动 Vivado，完成 BD 加载、模块引用刷新、设计验证、输出产品及 wrapper 生成，然后返回 `VALIDATED_INPUTS`；不启动综合和实现。`tmp/pv4` 已实际完成该流程。它与仅复制/检查输入的 `--prepare-only` 不同。不带这两个选项时仍执行完整硬件导出流程，时序失败继续拒绝BIT/XSA导出。其他仓库位置也应选短输出路径，脚本拒绝覆盖已有目录。

当前 `--prepare-only` 对144份启用输入执行隔离复制与摘要；两份停用的历史导出 XDC 不再进入构建输入。它不启动 Vivado。预检查同时核对启用的 XPR 引用、BD/IP版本、IP 文件精确大小写、实际执行的相机表、顶层/OOC 模型、BD 频率元数据及是否存在第二套输入延迟。`--inspect-only` 仅核对提交包硬件和历史报告身份。

[source_recovery.json](source_recovery.json) 是恢复时的来源及状态记录，记录完整 Git 提交号与恢复文件 SHA256。两份2026-10-24实现约束快照仍保存原字节，但现在停用；其相机、PS、像素时钟及层级派生约束与本次顶层/IP 生成约束重复。新构建使用当前启用的规范 XDC 和新生成的 IP/XPM 约束，不能将其他构建的导出快照当作规范源。

`pl2` 的综合和实现发生在相机模型校正之前，固定布线重分析也只在内存替换该检查点的相机模型。后续`pr1`已从校正后的144份原始有效输入完成一次真正的综合和布局布线；两类结果分别归档。

Windows 使用随包 `vivado_nocd.bat`，不直接调用安装目录的 `vivado.bat`，不改安装目录或系统配置。Linux 使用 PATH 中的 `vivado`。

## Windows工具脚本读取与隔离副本修复

用户`tmp/pl3`在`open_block_design`阶段失败：Vivado自带`aurora/bd.tcl`报`couldn't read file ...: No error`，未进入综合。该文件实际存在，17653字节，SHA256为`c2db3806400e4b250a3fadee39a094e3466ac06ae78b6e485b4b5f93c1cbe2df`，普通文件读取正常。直接在缺少规则引擎上下文的命名空间source会另报缺少`updater`，该探针结果不能当作安装文件损坏或原错误根因。

启动器现继承控制台的OS标准句柄，不再将它们重定向到Python打开的文件；完整输出由Vivado自带`-log`和`-journal`保留，终端也显示实时进度。该处理针对Windows Tcl文件通道的潜在重定向干扰；原`No error`的底层原因仍未得到确定证明。实际`tmp/pv4`随后完整通过BD/模块引用/输出产品准备，未再出现原错误。

同时修正了确定存在的隔离问题：Vivado会为缺失的停用XPR引用回找原工作区。现在先验证原始输入副本字节一致，再只在私有XPR中移除停用引用并重绑定工程路径，保留`source_color_test.xpr`原字节、源输入清单、工具接收的暂存输入清单及变换记录。144份有效输入保持不变；除了私有XPR之外，暂存文件不得变化。实际准备日志已无原工作区XDC回找。

失败与实际准备验证的原始日志与构建记录分别收录在 [reports/windows_loader_fix/](reports/windows_loader_fix/)。随后`pr1`在相同启动策略下实际走完综合/布局布线/报告；未修改Vivado安装文件、关闭规则或降级错误级别。

## 校正源码的实际综合与实现报告

[reports/final_camera_build/](reports/final_camera_build/) 保存实际`pr1`的原生报告、综合/布线DCP、有效约束、准备后BD、执行日志、源/暂存输入摘要、原始XPR及实际执行脚本。工具为Vivado2023.1、器件xc7z020clg400-2；从全新输出目录构建，没有复用旧综合/实现结果。原始输入中保留的AutoDCP引用没有启用增量综合/实现，原日志未声称增量复用。

| 指标 | 综合后 | 布局布线后 |
| --- | --- | --- |
| setup WNS / TNS | +0.079ns / 0ns | +0.021ns / 0ns |
| hold WHS / THS | −0.845ns / −3.145ns | **−0.844ns / −1.674ns** |
| hold失败端点 | 10 | 2 |
| 脉宽 WPWS / TPWS | +0.264ns / 0ns | +0.264ns / 0ns |
| LUT | 8720 / 53200（16.39%） | 7485 / 53200（14.07%） |
| FF | 11579 / 106400 | 10738 / 106400（10.09%） |
| BRAM tile | 15 / 140 | 15 / 140（10.71%） |
| DSP | 0 / 220 | 0 / 220 |

FCLK0/1/2配置为100/142.857/200MHz；相机使用上述名义HS140MHz/byte35MHz模型，工具量化周期为7.143/28.572ns。这里报告的是配置频率和STA条件，不是相机实测频率、实测FPS或已证明的最高工作频率。

`report_cdc`汇总无Critical条目，但保留CDC-6一条和CDC-15六十一条Warning；CDC-6位于VTG IP的多位寄存器同步路径。DRC为8条Warning；methodology为13条Warning，包含异步复位、Unknown CDC、缺失外部I/O delay及约束查询效率问题。此前的重复时钟约束告警已消失。原编译日志还保留未实例化ILA模块约束的Critical Warning及时序失败告警；没有屏蔽或将这些结果统一标为PASS。LP引脚及其他外部I/O的约束边界、复位/CDC结构仍须结合实际接口审阅。

此轮解决的是启动/隔离错误，并完成最终相机模型源码的报告复现流程。**hold仍未闭合**，报告完成不代表硬件技术验收通过。没有导出BIT/XSA、替换运行Overlay或执行板端操作。完整导出入口的负余量拒绝门槛仍保留。逐文件汇总清单已随清理前完整包留存；`reconstructed_staged_color_test.xpr`由原始XPR和记录的变换重建，SHA256与当时暂存清单中的XPR完全一致，未冒充Vivado保存后的工程文件。

## 模块引用加载修复

用户的 `tmp/pl1` 停在准备阶段：`open_bd_design` 加载 `axis_color_highlight` 时，先生成模块引用的 `component.xml` 和 `xgui/axis_color_highlight_v1_0.tcl`，再调用 IP 定制脚本；该次读取 XGUI 报文件不存在，而退出后的文件可读取。

旧入口将全部 Vivado 命令包在 `proc build_pl` 中。独立的真实 Vivado 2023.1 对照中，同样146份输入和路径长度在 Tcl 顶层加载成功，带 `reset_run` 的顶层对照也成功；局部过程调用又出现厂商相邻脚本 `utils.tcl` 解析失败。证据支持修正首次 BD/IP 初始化的调用作用域，不能据此认定 RTL 缺失或路径过长。

先前模块引用修复将构建命令移到 Tcl 顶层的 `catch` 中，更新编译顺序并刷新模块引用。用户随后实际运行的 `pl2` 已通过该阶段及综合、布局布线。本次另外修改的是相机模型、BD 频率元数据和约束启用状态；没有修改 RTL、IDELAY 值或板端相机表。

## 历史15%～85%相机模型与固定布线 hold 检查

以运行时真正读取的 `hardware.json` 中 `sensor_init`、`sensor_mode` 为依据，而非未使用的 Python 默认表。最终配置为3034=1a、3035=21、3036=46、3037=05、3108=11、4837=24，两 lane、1280×720 RAW10。历史实板读回与这些寄存器一致；12MHz XVCLK 是此前用户确认的模组名义参考。来源原文件保存在 [timing_evidence/](timing_evidence/)，并由构建入口检查 SHA256。

| 量 | 名义值与工具实际输入 |
| --- | --- |
| HS / lane / byte | 140MHz / 280Mb/s / 35MHz |
| 时钟周期 T / UI | 50/7ns / 25/7ns；Vivado 1ps网格使用7.143ns周期、3.571ns下降沿。 |
| 输入 min / max | 15/28ns / 85/28ns，按1ps向保守方向取整为0.535ns / 3.036ns。 |
| 包络性质 | 沿用15%/85%UI工程假设，覆盖P/N及两个DDR参考边沿。 |

顶层 `system.xdc` 统一拥有相机时钟与输入延迟；IP 的 scoped clocks 文件不再追加旧数值；仅用于 IP OOC 的 XDC 使用同一模型和 IP 端口名。BD 的外部时钟元数据也同步为140MHz。该次历史min/max按同一UI换算；后续经用户授权的包络变更及结果见本文最新结果。

实际 Vivado2023.1 固定布线重分析保存在 [reports/camera_model_reanalysis/](reports/camera_model_reanalysis/)。两 lane×P/N×Fast/Slow×数据rise/fall×setup/hold共32组查询、128条路径均覆盖；时钟/数据IDELAY仍为0/12/12 tap，位置不变。

其中 [inputs/pl2_reports/](reports/camera_model_reanalysis/inputs/pl2_reports/) 是模型校正前的同次原始综合/实现报告，原始命令、输入摘要、日志和routed DCP一并保留。`pl2`原资源为LUT7485/53200、FF10738/106400、BRAM15/140、DSP0；其时序为setup+0.303ns、hold−1.111ns，不能与下表混写成同一模型。历史逐文件汇总清单已随清理前完整包留存；当前构建校验保留在 `reports/sampling_window_build/`。

| 指标 | 固定布线重分析结果 |
| --- | --- |
| MIPI最差setup | +0.021ns |
| MIPI最差hold | **−0.844ns，FAIL**；Slow角点仍有缺口。 |
| 工具量化的byte周期 | 28.572ns，来自HS时钟÷4。 |
| 结论范围 | 既有路由、只替换相机输入模型的重新STA；其他历史DCP约束保留。不是校正源码的干净重建，也没有导出硬件。 |

可在任意PowerShell目录复现同一检查点的诊断：

```powershell
$repo = 'D:/Workspace/AMD_camera/FPGA-main/FPGA-main'
$pkg = "$repo/output/submission/pynq_web_v14"
$env:XILINX_VIVADO = 'D:/Xilinx/Vivado/2023.1'
& "$pkg/build/vivado_nocd.bat" -mode batch -notrace `
  -log "$repo/tmp/ct2.log" -journal "$repo/tmp/ct2.jou" `
  -source "$pkg/build/check_camera_timing.tcl" `
  -tclargs "$pkg/build/reports/camera_model_reanalysis/inputs/routed.dcp" `
  "$pkg/build/reports/camera_model_reanalysis/inputs/corrected_system.xdc" "$repo/tmp/ct2"
```

`tmp/ct2` 及对应日志必须全新。`ANALYZED`只表示诊断完成，`sampling_summary.tsv`仍应保留`timing_status=FAIL`。不进行tap扫描、重新布局布线、DCP保存、BIT导出或板端访问。首次诊断因保护条件未考虑工具1ps量化而提前停止，失败日志保留在主机工作目录；上述归档为修正保护条件后的实际结果。

## 同次构建输出

| 路径（相对新输出目录） | 内容 |
| --- | --- |
| `inputs/project/` | 独立输入副本；Vivado只写副本和新工程。 |
| `build.json`、`vivado.log`、`vivado.jou` | 命令、脚本摘要、工具退出码、阶段、时序状态及原生日志；标准输出继承终端，不再创建Python重定向的console.log。历史构建已有的console.log仍原样保留。 |
| `input_manifest.tsv`、`staged_input_manifest.tsv`、`source_color_test.xpr` | 原始有效源码与工具输入的分别摘要、原始XPR；私有XPR变换见build.json。 |
| `vivado/reports/` | 综合/实现资源和时序、时钟关系、CDC、DRC、methodology及setup/hold门槛。 |
| `vivado/checkpoints/` | 同次综合和布线检查点。 |
| `vivado/effective_constraints.xdc`、`vivado/prepared_bd.tcl` | 实际约束与准备后的 BD。 |
| `vivado/artifacts/system_wrapper.bit` | 本次工程生成的 BIT。 |
| `vivado/artifacts/system_wrapper.xsa` | 同一实现导出的含 BIT 的 XSA。 |
| `vivado/artifacts/system_wrapper.hwh` | 校验 XSA 内 BIT 一致后，从同一 XSA 提取的 HWH。 |

setup、hold或时序汇总未通过时不进入BIT/XSA导出；保留失败报告和检查点。`--reports-only`的`REPORTS_COMPLETE`仅表示报告流程完成，`timing_status=FAIL`、违例详情和原始报告必须保留；BD/综合/布线或报告生成错误仍返回FAILED。即使报告模式时序为PASS，也不导出硬件，CDC/DRC仍需审阅。完整导出入口成功也只代表候选构建，不自动替换运行目录或建立板端准入。

`python -B sim/test_pl_flow.py` 验证导出控制流、失败门槛与 XSA 配对校验，执行环境为主机模拟，不代表 RTL、综合、实现或上板通过。
