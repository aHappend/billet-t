# BILLET-T1 (Gen-1 (v3.0))

[English](README.md) · [简体中文](README.zh-CN.md) · [Family Home](../../README.md) · [**Full Engineering Report (`REPORT.pdf`)**](REPORT.pdf)

## Overview

256-point fixed-point Radix-2 complex FFT · Ping-pong frame SRAM, bit-reversal addressing & twiddle butterfly pipeline.

This directory contains the **Vulcan 3.0 full-shell silicon release** of `BILLET-T1`, verified end-to-end through cycle-accurate simulation, negative-control mutation testing, matched `AMD EPYC 7662` CPU and `NVIDIA Tesla V100` GPU benchmarking, 4-corner full-shell Quartus Prime 17.1 static timing closure on Intel Arria 10 GX (`10AX115N3F40E2SG`), and physical PCIe Gen3x8 + DDR4-2133 hardware-in-the-loop (`board_hil`) execution.

## Physical Silicon Signoff Summary

| Metric | Verified Full-Shell Result |
| :--- | :--- |
| **Target FPGA Device** | Intel Arria 10 GX `10AX115N3F40E2SG` |
| **Platform Integration Scope** | Full PCIe Gen3x8 + DDR4-2133 Platform Shell (All 95 Active Clocks Closed) |
| **Core Clock STA (`100 MHz` Target)** | **`132.96 MHz`** (`WNS +2.479 ns`, `WHS +0.013 ns`) |
| **PCIe / DDR4 Clock Closure** | PCIe `coreclkout`: **`278.24 MHz`** · DDR4 `usr_clk`: **`276.78 MHz`** |
| **Whole-Shell Resource Utilization** | `42,670 / 427,200 ( 10 % ) ALMs` · `3 / 1,518 ( < 1 % ) DSPs` · `189 / 2,713 ( 7 % ) M20K` |
| **Physical Board HIL (`PCIe Gen3x8 + DDR4`)** | **PASSED** (`rpd_sha256: b78ee9218a29fbd4…`, `3` deterministic runs) |

## Directory Contents

- [`REPORT.pdf`](REPORT.pdf) — Complete engineering report (architecture, RTL design, verification matrix, 4-corner STA, physical HIL, and matched CPU/GPU benchmarks)
- [`rtl/`](rtl/) — Synthesizable SystemVerilog RTL and timing constraints (`14` files)
- [`tests/`](tests/) — Verification testbenches, reference models, and matched CPU/GPU/HIL harnesses (`13` files)
- [`evidence/`](evidence/) — Public post-fit STA ([`quartus-sta-summary.json`](evidence/quartus-sta-summary.json)) and physical board HIL ([`board-hil-summary.json`](evidence/board-hil-summary.json)) receipts
