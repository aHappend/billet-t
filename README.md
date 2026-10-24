<div align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="brand/logo-dark.svg">
    <img src="brand/logo.svg" width="420" alt="Vulcan">
  </picture>
  <h1>Billet-T · Spectral & Transform DSP Silicon</h1>
  <p><strong>Synthesizable 100 MHz+ Fixed-Point FFT, IFFT & Multichannel Power-Spectrum Accelerators · Intel Arria 10 GX PCIe Gen3x8 HIL</strong></p>
  <p>
    <img src="https://img.shields.io/badge/Platform-Intel_Arria_10_GX-0f766e?style=flat-square" alt="Platform">
    <img src="https://img.shields.io/badge/Quartus_17.1_STA-100_MHz%2B_Closed-0f766e?style=flat-square" alt="STA">
    <img src="https://img.shields.io/badge/PCIe_Gen3x8_HIL-100%25_Passed-1d4ed8?style=flat-square" alt="HIL">
    <img src="https://img.shields.io/badge/Author-Sufeng_Guo_(MSRA)-334155?style=flat-square" alt="Author">
    <img src="https://img.shields.io/badge/License-MIT-64748b?style=flat-square" alt="License">
  </p>
  <p>
    <a href="https://ahappend.github.io/vulcan/">Website</a> ·
    <a href="https://github.com/aHappend/vulcan-showcase">Vulcan Showcase</a> ·
    <a href="https://github.com/aHappend/anvil-q">Anvil-Q (LLM)</a> ·
    <a href="https://github.com/aHappend/anvil-e">Anvil-E (Embedding)</a> ·
    <a href="https://github.com/aHappend/billet-t">Billet-T (FFT/DSP)</a> ·
    <a href="https://github.com/aHappend/billet-f">Billet-F (FIR/IIR)</a> ·
    <a href="https://github.com/aHappend/rivet-a">Rivet-A (AES-GCM)</a> ·
    <a href="https://github.com/aHappend/rivet-h">Rivet-H (SHA/HMAC)</a> ·
    <a href="README.zh-CN.md"><strong>中文文档</strong></a>
  </p>
</div>

---

**Billet** is the digital signal processing (DSP) silicon family in Vulcan's seven-family workshop matrix. **Billet-T** delivers synthesizable `100 MHz+` spectral transform engines spanning 256-point Radix-2 FFT (`BILLET-T1`), runtime-configurable 64/128/256/512-point FFT/IFFT (`BILLET-T2`), and 4-channel windowed 50%-overlap STFT power-spectrum estimation (`BILLET-T3`).

## Silicon Signoff Matrix & Dual-Track Publications (`100 MHz+` Baseline)

| Gen | Accelerator | Architecture & Numerical Scope | Quartus 17.1 STA (`10.0 ns`) | Intel Arria 10 GX Utilization | PCIe Gen3x8 HIL | Academic & Developer Reports |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **Gen-1** | [**BILLET-T1**](billet-t1/) | 256-Point Fixed-Point Radix-2 Complex FFT · Double-Buffered Ping-Pong Memory & Bit-Reversal | `128.29 MHz` (`WNS +2.205 ns`) | `4,120 ALMs (0.96%) · 16 DSPs (1.05%) · 16 M20K` | **PASSED (3/3)** | [**Whitepaper PDF**](billet-t1/SHOWCASE_REPORT.pdf) · [**Engineering PDF**](billet-t1/REPORT.pdf) |
| **Gen-2** | [**BILLET-T2**](billet-t2/) | Runtime-Configurable 64/128/256/512-Point FFT/IFFT · Stage-by-Stage Schedule & `1/N` Scaling | `141.42 MHz` (`WNS +2.929 ns`) | `5,480 ALMs (1.28%) · 24 DSPs (1.58%) · 24 M20K` | **PASSED (3/3)** | [**Whitepaper PDF**](billet-t2/SHOWCASE_REPORT.pdf) · [**Engineering PDF**](billet-t2/REPORT.pdf) |
| **Gen-3** | [**BILLET-T3**](billet-t3/) | 4-Channel Windowed 50%-Overlap STFT & Power-Spectrum (`|X[k]|^2`) Engine | `141.42 MHz` (`WNS +2.929 ns`) | `7,860 ALMs (1.84%) · 32 DSPs (2.11%) · 36 M20K` | **PASSED (3/3)** | [**Whitepaper PDF**](billet-t3/SHOWCASE_REPORT.pdf) · [**Engineering PDF**](billet-t3/REPORT.pdf) |

## Academic Product Whitepaper Visual Gallery

### BILLET-T1 · Academic Whitepaper Preview ([`billet-t1/SHOWCASE_REPORT.pdf`](billet-t1/SHOWCASE_REPORT.pdf))
<table>
  <tr>
    <td align="center" width="33%"><a href="billet-t1/SHOWCASE_REPORT.pdf"><img src="billet-t1/showcase_figures/page-1.png" width="100%" alt="BILLET-T1 Page 1"></a><br><sub><strong>Page 1 · Architecture & KPI Summary</strong></sub></td>
    <td align="center" width="33%"><a href="billet-t1/SHOWCASE_REPORT.pdf"><img src="billet-t1/showcase_figures/page-2.png" width="100%" alt="BILLET-T1 Page 2"></a><br><sub><strong>Page 2 · Experimental Benchmarks & Parity</strong></sub></td>
    <td align="center" width="33%"><a href="billet-t1/SHOWCASE_REPORT.pdf"><img src="billet-t1/showcase_figures/page-3.png" width="100%" alt="BILLET-T1 Page 3"></a><br><sub><strong>Page 3 · Arria 10 STA, HIL & Scaling</strong></sub></td>
  </tr>
</table>

### BILLET-T2 · Academic Whitepaper Preview ([`billet-t2/SHOWCASE_REPORT.pdf`](billet-t2/SHOWCASE_REPORT.pdf))
<table>
  <tr>
    <td align="center" width="33%"><a href="billet-t2/SHOWCASE_REPORT.pdf"><img src="billet-t2/showcase_figures/page-1.png" width="100%" alt="BILLET-T2 Page 1"></a><br><sub><strong>Page 1 · Architecture & KPI Summary</strong></sub></td>
    <td align="center" width="33%"><a href="billet-t2/SHOWCASE_REPORT.pdf"><img src="billet-t2/showcase_figures/page-2.png" width="100%" alt="BILLET-T2 Page 2"></a><br><sub><strong>Page 2 · Experimental Benchmarks & Parity</strong></sub></td>
    <td align="center" width="33%"><a href="billet-t2/SHOWCASE_REPORT.pdf"><img src="billet-t2/showcase_figures/page-3.png" width="100%" alt="BILLET-T2 Page 3"></a><br><sub><strong>Page 3 · Arria 10 STA, HIL & Scaling</strong></sub></td>
  </tr>
</table>

### BILLET-T3 · Academic Whitepaper Preview ([`billet-t3/SHOWCASE_REPORT.pdf`](billet-t3/SHOWCASE_REPORT.pdf))
<table>
  <tr>
    <td align="center" width="33%"><a href="billet-t3/SHOWCASE_REPORT.pdf"><img src="billet-t3/showcase_figures/page-1.png" width="100%" alt="BILLET-T3 Page 1"></a><br><sub><strong>Page 1 · Architecture & KPI Summary</strong></sub></td>
    <td align="center" width="33%"><a href="billet-t3/SHOWCASE_REPORT.pdf"><img src="billet-t3/showcase_figures/page-2.png" width="100%" alt="BILLET-T3 Page 2"></a><br><sub><strong>Page 2 · Experimental Benchmarks & Parity</strong></sub></td>
    <td align="center" width="33%"><a href="billet-t3/SHOWCASE_REPORT.pdf"><img src="billet-t3/showcase_figures/page-3.png" width="100%" alt="BILLET-T3 Page 3"></a><br><sub><strong>Page 3 · Arria 10 STA, HIL & Scaling</strong></sub></td>
  </tr>
</table>

## Vulcan Seven-Family Workshop Silicon Matrix

| Silicon Family | Workshop Metaphor | Domain & Series Repositories |
| :--- | :--- | :--- |
| **Anvil** *(Primary Focus)* | Heavy forge anvil bearing core compute loads | AI & Large-Model Compute — [**Anvil-Q** (Quantized LLMs)](https://github.com/aHappend/anvil-q) · [**Anvil-E** (Multimodal Embeddings)](https://github.com/aHappend/anvil-e) |
| **Billet** | Raw metal stock shaped and combined into systems | Digital Signal Processing — [**Billet-T** (FFT/Spectral)](https://github.com/aHappend/billet-t) · [**Billet-F** (FIR/SOS-IIR Filters)](https://github.com/aHappend/billet-f) |
| **Rivet** | Small, critical, rock-solid fasteners | Cryptography & Data Integrity — [**Rivet-A** (AES/GCM/DMA)](https://github.com/aHappend/rivet-a) · [**Rivet-H** (SHA-256/512/HMAC)](https://github.com/aHappend/rivet-h) |
| **Swage** | Die-forming tool shaping inputs into target forms | Image Processing & ISP — **Swage-S** (2D Scaler, 3×3 Spatial Filter, Bayer Demosaic, CSC) |
| **Bellows** | Expanding/contracting continuous airflow | Streaming Data Compression — **Bellows-L** (LZ4 Decompressor, Hash-Table Compressor, XXH32 DMA) |
| **Crucible** | Vessel fusing diverse materials into form | Graphics Processing & Rendering (Geometry, Texture & Lighting Fusion) |
| **Furnace** | Industrial furnace integrating multiple stages | Heterogeneous SoCs & Complete Multi-Engine Compute Subsystems |

---
<p align="center"><sub>Author: <strong>Sufeng Guo</strong> · Microsoft Research Asia · <a href="mailto:sufeng_guo@smail.nju.edu.cn">sufeng_guo@smail.nju.edu.cn</a> · <a href="LICENSE">MIT License</a></sub></p>
