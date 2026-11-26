# BILLET-T1（Gen-1 (v3.0)）

[简体中文](README.zh-CN.md) · [English](README.md) · [返回家族主页](../../README.zh-CN.md) · [**完整工程报告（`REPORT.pdf`）**](REPORT.pdf)

## 概览

256 点定点基-2 复数 FFT 引擎 · 乒乓双缓冲帧 SRAM、位反转寻址与旋转因子蝶形流水线。

本目录发布 `BILLET-T1` 的 **Vulcan 3.0 满血全壳物理上板版本**，已完成周期精确仿真、负向故障注入测试、同口径 `AMD EPYC 7662` CPU 与 `NVIDIA Tesla V100` GPU 基准对照、Intel Arria 10 GX（`10AX115N3F40E2SG`）全平台外壳四温度电压角 Quartus Prime 17.1 静态时序收敛，以及真实 PCIe Gen3x8 + DDR4-2133 物理板卡在环（`board_hil`）实测。

## 物理板级签核摘要

| 指标维度 | 全壳实测签核结果 |
| :--- | :--- |
| **目标 FPGA 器件** | Intel Arria 10 GX `10AX115N3F40E2SG` |
| **平台集成边界** | 完整 PCIe Gen3x8 + DDR4-2133 平台外壳（全部 95 个活动时钟域四温度角闭合） |
| **主核时钟收敛（目标 `100 MHz`）** | **`132.96 MHz`**（建立裕量 `+2.479 ns`，保持裕量 `+0.013 ns`） |
| **PCIe / DDR4 时钟域收敛** | PCIe `coreclkout`：**`278.24 MHz`** · DDR4 `usr_clk`：**`276.78 MHz`** |
| **含外壳整芯片资源占用** | `42,643 / 427,200 ( 10 % ) ALMs` · `3 / 1,518 ( < 1 % ) DSPs` · `189 / 2,713 ( 7 % ) M20K` |
| **物理板卡上板闭环（`board_hil`）** | **实测通过**（镜像校验 `b78ee9218a29fbd4…`） |

## 目录结构

- [`REPORT.pdf`](REPORT.pdf) — 完整技术与工程验证报告（微架构、RTL 实现、验证矩阵、四角 STA、物理上板回执与同机 CPU/GPU 实测对比）
- [`rtl/`](rtl/) — 可综合 SystemVerilog 源码与时序约束（共 `13` 个文件：`Role_BilletT1.sv`, `billet_t1_bitrev.sv`, `billet_t1_buffer_sched.sv`, `billet_t1_butterfly.sv`, `billet_t1_frame_ram.sv`, `billet_t1_mailbox.sv`, `billet_t1_pkg.sv`, `billet_t1_reset_sync.sv`, `billet_t1_role_dma.sv`, `billet_t1_top.sv`, `billet_t1_twiddle_rom.sv`, `vulcan_role.sdc`, `vulcan_role.sv`）
- [`tests/`](tests/) — 独立验证平台、参考模型及同口径 CPU/GPU 基准源码（共 `10` 个文件）
- [`evidence/`](evidence/) — 全壳静态时序签核（[`quartus-sta-summary.json`](evidence/quartus-sta-summary.json)）与物理板卡实测（[`board-hil-summary.json`](evidence/board-hil-summary.json)）公开摘要回执
