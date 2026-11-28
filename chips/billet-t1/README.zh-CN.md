# BILLET-T1（Gen-1 (v3.0)）

[简体中文](README.zh-CN.md) · [English](README.md) · [返回家族主页](../../README.zh-CN.md) · [**完整工程签核报告（`REPORT.pdf`）**](REPORT.pdf)

## 芯片概述

256 点定点基 2 复数快速傅里叶变换（FFT）芯片 · 乒乓帧缓存 SRAM、位反转寻址与旋转因子蝶形流水线。

本目录收录 `BILLET-T1` 的 **Vulcan 3.0 全壳物理硅片发布版**，已完成周期精确仿真、反向单比特故障注入检验、同口径 `AMD EPYC 7662` CPU 与 `NVIDIA Tesla V100` GPU 对照评测、Intel Arria 10 GX（`10AX115N3F40E2SG`）Quartus Prime 17.1 全壳四温度电压角静态时序闭合，以及物理板卡 PCIe Gen3x8 + DDR4-2133 硬件在环（`board_hil`）实测通过。

## 物理硅片签核指标摘要

| 签核维度 | 全壳实测结果 |
| :--- | :--- |
| **目标 FPGA 器件** | Intel Arria 10 GX `10AX115N3F40E2SG` |
| **平台外壳集成范围** | 完整 PCIe Gen3x8 + DDR4-2133 平台外壳（全片 95 个活动时钟域全部闭合） |
| **核心时钟签核（`100 MHz` 目标）** | **`132.96 MHz`**（`WNS +2.479 ns`，`WHS +0.013 ns`） |
| **PCIe / DDR4 接口时钟闭合** | PCIe `coreclkout`：**`278.24 MHz`** · DDR4 `usr_clk`：**`276.78 MHz`** |
| **含外壳整芯片资源占用** | `42,670 / 427,200 ( 10 % ) ALMs` · `3 / 1,518 ( < 1 % ) DSPs` · `189 / 2,713 ( 7 % ) M20K` |
| **物理板卡 HIL（`PCIe Gen3x8 + DDR4`）** | **实测通过**（`rpd_sha256: b78ee9218a29fbd4…`，`3` 轮确定性逐字节一致） |

## 目录文件说明

- [`REPORT.pdf`](REPORT.pdf) — 完整工程签核报告（体系结构、RTL 微架构、验证矩阵、四角静态时序、真机上板与同口径 CPU/GPU 基准测试）
- [`rtl/`](rtl/) — 可综合 SystemVerilog RTL 源码与时序约束文件（共 `14` 个文件）
- [`tests/`](tests/) — 自检测试平台、黄金参考模型与 CPU/GPU/上板评测脚本（共 `13` 个文件）
- [`evidence/`](evidence/) — 布局布线后静态时序（[`quartus-sta-summary.json`](evidence/quartus-sta-summary.json)）与真机上板实测（[`board-hil-summary.json`](evidence/board-hil-summary.json)）公开凭证
