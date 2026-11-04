# Linux/PYNQ应用开发技能包

版本：2026-11-02。此目录是完整工程提交中 `skill/` 子包的独立可复用版本，按《全国大学生嵌入式芯片与系统设计竞赛2026 选题指南（AMD）》第 3.3.5.2 节整理。

## 使用

- 阅读 [`skill/README.md`](skill/README.md)，按问题选择七项技能；通用PYNQ应用从pynq-development开始，新建HLS/BD工程按需使用pynq-accelerator-flow。
- 在包根目录运行：`python -B skill/scripts/verify_package.py skill`。
- `verification.txt` 保存打包时的离线结果；`manifest.json` 保存每个文件的大小和 SHA256。
- 核心检查与DMA替身使用Python标准库；可选Python/native数组示例需要已有NumPy，缺失时明确跳过。离线命令不导入PYNQ或连接设备，不修改运行工程配置。
- 模板 Tcl 语法检查使用 tkinter/Tcl；真实 C ABI 测试需要已有 NumPy 和 GCC/Clang，缺失明确跳过。硬件构建、目标 IRQ 与冷启动分别验收。

## 与完整参赛工程的关系

图片中的 3.3.5.1 工程包还要求 RTL/HLS/PS 源码、仿真/验证结果、综合实现报告、上板输入输出和可复现构建；这些属于原工程的 `src/`、`sim/`、`build/`、`board/`、`data/`、`report/` 等目录，本 ZIP 只交付可独立复用的 `skill/` 子包。完整工程提交时应将本目录的 `skill/` 合并到工程根目录，并在总 README 中指明源码、报告和协作记录的位置。

## 复用边界

`skill/references/project-context.md`保留旧工程快照，不作为当前Linux/PYNQ默认路线。七项技能包含通用PYNQ开发入口与专项方法，说明场景、方法、边界和来源；跨板卡、真实库或硬件结论分别验证。`skill/references/submission-requirements.md`对照了提交要求。

打包前旧版技能目录已保存到 Git 分支 `codex/archive-skill-package-20261028`，提交 `fd796cdbdde8a65dca614eccaeffc4cc6efbe2b2`。
