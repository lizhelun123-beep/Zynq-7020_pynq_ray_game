---
name: xilinx-project-flow
description: 按Linux/PYNQ应用、Overlay或硬件变更路由工具链，核对BIT/HWH与实际版本、来源及输出；XSA/ELF/BOOT仅用于实际需要的平台或启动交付。
---

# AMD/Xilinx 工具链与制品交接

默认服务现有Linux/PYNQ应用与Overlay交付。先确认目标阶段，不因提到FPGA就启动全部工具链。应用开发读 [PYNQ入口](../pynq-development/SKILL.md)；已有工程的路径线索见 [工程地图](references/project-map.md)，制品核对见 [交接证据门](references/evidence-gates.md)。

## 使用方法

1. 从实际工程读取目标板卡/器件、工具版本、处理器/ABI、入口脚本、硬件输入及输出目标。未知项列出待证，不能猜地址、时钟、IP 版本或 sysroot。
2. Python应用/配置先走用户态代码与离线验证；原生C/C++按实际目标ABI编译并复用现有库/核心。确有RTL/BD/IP/XDC变化时才进入最小验证与硬件流程。Linux/PYNQ应用更新不自动生成BOOT，也不默认重建内核/rootfs。
3. Overlay交付沿源码/配置/脚本绑定BIT/HWH与接口；平台需要时附XSA。只有明确启动镜像任务才核对ELF/FSBL/BOOT。记录实际命令、日志、指纹与配套证据，哈希不独自证明同代或兼容。
4. 保留已有修改和产物。替换有价值旧说明/实现前按目标仓库规则归档；构建输出使用新目录，不覆盖已交付基线。先检查前置依赖再启动工具，失败保留最小诊断。
5. 分开记录静态、host、ARM 编译/链接、BOOT 分区和实际上板结果。ELF 能链接、BOOT 能组合不等于冷启动成功或游戏实时通过。
6. 完整实现、下载/复位、SD 写入、设备/服务变更按当前任务授权执行。同一原因两次无新信息时停止该路径，给出能增加信息的下一步。

## 可复制提示词

```text
使用 $xilinx-project-flow。目标阶段/结果：填写需要生成或核对的产物。
已有输入：填写实际板卡、Linux/PYNQ/工具版本、canonical工程、BIT/HWH和应用入口；平台/启动任务再提供XSA/FSBL。
先确认是否只需用户态应用修改或原生核心编译，再复用现有脚本完成本次已授权范围。
给出命令、前置条件、日志和输出身份，明确哪些检查已运行、哪些尚未上板。
不复制工程、不覆盖旧制品、不因生成 BOOT 自动写 SD 或重建 PL。
```

## 失效条件与示例

硬件输入无法绑定、ABI/器件不匹配、输出目录已含未知制品、旧报告对应不同配置，或工具版本不明时，不能交接为完整通过。

例如，Linux/PYNQ只改用户态协议编码或算法包装时，复用现有BIT/HWH与驱动，先验证应用；涉及原生C时才按目标ABI编译对应库/程序。历史Standalone生成BOOT的流程见末节，不套用于PYNQ用户态应用。换题或换板后重新核准实际镜像、处理器和工具环境，不照抄旧命令。

## 经验来源与已验证效果

历史工程 version14 用 Vitis 2023.1 与冻结的 live12 平台生成新应用/BOOT，记录包含ARM/EABI/DDR、新协议符号和三分区逐字节校验；没有运行完整Vivado。原文见 [project-evidence.json](../references/project-evidence.json) 的 `binary_wire_v3_delivery_20261028`。这些是旧路线证据，本轮未重跑ARM或打包固件。外部参考适配见 [source-adaptation.md](references/source-adaptation.md)。
