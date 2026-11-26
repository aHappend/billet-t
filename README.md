<div align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="brand/logo-dark.svg">
    <img src="brand/logo.svg" width="420" alt="Vulcan">
  </picture>
  <h1>Billet-T · Spectral & Transform DSP Silicon</h1>
  <p><strong>Synthesizable 100 MHz+ Fixed-Point Radix-2 FFT/IFFT & Spectral Accelerators · Intel Arria 10 GX Full-Shell STA & PCIe Gen3x8 HIL</strong></p>
  <p>
    <img src="https://img.shields.io/badge/Target_FPGA-Intel_Arria_10_GX_(10AX115N3F40E2SG)-0f766e?style=flat-square" alt="FPGA">
    <img src="https://img.shields.io/badge/Full--Shell_STA-4--Corner_100_MHz%2B_Closed-0f766e?style=flat-square" alt="STA">
    <img src="https://img.shields.io/badge/Physical_Board_HIL-PCIe_Gen3x8_%2B_DDR4_Passed-1d4ed8?style=flat-square" alt="HIL">
    <img src="https://img.shields.io/badge/Benchmarks-Matched_EPYC_CPU_%26_V100_GPU-334155?style=flat-square" alt="Benchmarks">
    <img src="https://img.shields.io/badge/License-MIT-64748b?style=flat-square" alt="License">
  </p>
  <p>
    <a href="https://github.com/aHappend/vulcan-showcase"><strong>Vulcan Showcase</strong></a> · <a href="https://github.com/aHappend/bellows-l">Bellows-L (LZ4)</a> · <a href="https://github.com/aHappend/billet-t">Billet-T (FFT)</a> · <a href="https://github.com/aHappend/billet-f">Billet-F (FIR)</a> · <a href="https://github.com/aHappend/crucible-g">Crucible-G (3D)</a> · <a href="https://github.com/aHappend/furnace-x">Furnace-X (DMA/CRC)</a> · <a href="https://github.com/aHappend/hammer-v">Hammer-V (RISC-V)</a> · <a href="https://github.com/aHappend/rivet-a">Rivet-A (AES-GCM)</a> · <a href="https://github.com/aHappend/rivet-h">Rivet-H (SHA-256)</a> · <a href="https://github.com/aHappend/swage-s">Swage-S (ISP)</a> · <a href="https://github.com/aHappend/sable">SABLE</a> · <a href="README.zh-CN.md"><strong>简体中文</strong></a>
  </p>
</div>

---

**Billet-T** is the spectral-transform line of the Billet DSP family, delivering bit-reversed ping-pong SRAM scheduling, twiddle-ROM complex butterfly pipelines, and PCIe/DDR4 frame DMA (`BILLET-T1`).

## Vulcan 3.0 Full-Shell Silicon Signoff Matrix

All chips in `chips/` are synthesized, placed, routed, and timing-closed inside the **complete Intel Arria 10 GX PCIe Gen3x8 + DDR4-2133 platform shell** (`10AX115N3F40E2SG`, Quartus Prime Standard `17.1.0`) and executed on physical board hardware (`board_hil`) alongside matched `AMD EPYC 7662` CPU and `NVIDIA Tesla V100` GPU baselines.

| Generation | Chip | Architecture & Verification Scope | Full-Shell 4-Corner STA | Whole-Shell Utilization (`10AX115`) | Physical Board HIL | Deliverables |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **Gen-1 (v3.0)** | [**BILLET-T1**](chips/billet-t1/) | 256-point fixed-point Radix-2 complex FFT · Ping-pong frame SRAM, bit-reversal addressing & twiddle butterfly pipeline | **`132.96 MHz`** (`WNS +2.479 ns`)<br><sub>PCIe `278.24` · DDR4 `276.78 MHz`</sub> | `42,643 ALMs (10%)`<br><sub>`3 DSPs` · `189 M20K`</sub> | **PASSED**<br><sub>PCIe Gen3x8 + DDR4</sub> | [**`REPORT.pdf`**](chips/billet-t1/REPORT.pdf) · [RTL](chips/billet-t1/rtl/) |

## Engineering Report Visual Preview

### BILLET-T1 · Vulcan 3.0 Engineering Report Preview ([`chips/billet-t1/REPORT.pdf`](chips/billet-t1/REPORT.pdf))
<table>
  <tr>
    <td align="center" width="33%"><a href="chips/billet-t1/REPORT.pdf"><img src="chips/billet-t1/report_preview/page-1.png" width="100%" alt="BILLET-T1 Page 1"></a><br><sub><strong>Page 1 · Executive Summary & Architecture</strong></sub></td>
    <td align="center" width="33%"><a href="chips/billet-t1/REPORT.pdf"><img src="chips/billet-t1/report_preview/page-2.png" width="100%" alt="BILLET-T1 Page 2"></a><br><sub><strong>Page 2 · Microarchitecture & Verification</strong></sub></td>
    <td align="center" width="33%"><a href="chips/billet-t1/REPORT.pdf"><img src="chips/billet-t1/report_preview/page-3.png" width="100%" alt="BILLET-T1 Page 3"></a><br><sub><strong>Page 3 · Full-Shell STA, HIL & Benchmarks</strong></sub></td>
  </tr>
</table>

## Clean Repository Structure

```text
billet-t/
├── README.md               # Formal English documentation
├── README.zh-CN.md         # Formal Simplified Chinese documentation
├── brand/                  # Light/dark vector identity assets
├── chips/
│   └── billet-t1/          # BILLET-T1 (RTL, tests, STA/HIL receipts, REPORT.pdf)
├── archive-v2/             # Deduplicated pre-3.0 historical design snapshots
└── LICENSE                 # MIT License
```

## Historical Pre-3.0 Archive (`archive-v2/`)

Earlier pre-3.0 exploration snapshots ([`billet-t2`](archive-v2/billet-t2/), [`billet-t3`](archive-v2/billet-t3/)) are retained cleanly under [`archive-v2/`](archive-v2/README.md) with explicit standalone/simulation scope boundaries, separate from the full-shell silicon-verified `chips/` lineup above.
