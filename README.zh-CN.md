<div align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="brand/logo-dark.svg">
    <img src="brand/logo.svg" width="420" alt="Vulcan">
  </picture>
  <h1>Billet-T · 快速傅里叶变换与频域信号处理芯片家族</h1>
  <p><strong>可综合 100 MHz+ 定点复数基 2 蝶形 FFT 与乒乓帧缓存流式引擎 · Intel Arria 10 GX 真机闭环验证</strong></p>
  <p>
    <img src="https://img.shields.io/badge/目标器件-Intel_Arria_10_GX_(10AX115N3F40E2SG)-0f766e?style=flat-square" alt="FPGA">
    <img src="https://img.shields.io/badge/全壳时序签核-四温度角_100_MHz%2B_闭合-0f766e?style=flat-square" alt="STA">
    <img src="https://img.shields.io/badge/物理板卡_HIL-PCIe_Gen3x8_%2B_DDR4-1d4ed8?style=flat-square" alt="HIL">
    <img src="https://img.shields.io/badge/异构对标-同口径_EPYC_CPU_与_V100_GPU-334155?style=flat-square" alt="Benchmarks">
    <img src="https://img.shields.io/badge/开源协议-MIT-64748b?style=flat-square" alt="License">
  </p>
  <p>
    <a href="https://github.com/aHappend/vulcan-showcase"><strong>Vulcan 总览</strong></a> · <a href="https://github.com/aHappend/anvil-q">Anvil-Q (LLM)</a> · <a href="https://github.com/aHappend/anvil-e">Anvil-E (编码器)</a> · <a href="https://github.com/aHappend/anvil-en">Anvil-EN (Gemma)</a> · <a href="https://github.com/aHappend/anvil-d">Anvil-D (MLA/MoE)</a> · <a href="https://github.com/aHappend/anvil-qn">Anvil-QN (Qwen3)</a> · <a href="https://github.com/aHappend/bellows-l">Bellows-L</a> · <a href="https://github.com/aHappend/bellows-n">Bellows-N</a> · <a href="https://github.com/aHappend/billet-f">Billet-F</a> · <a href="https://github.com/aHappend/billet-t">Billet-T</a> · <a href="https://github.com/aHappend/crucible-g">Crucible-G</a> · <a href="https://github.com/aHappend/furnace-x">Furnace-X</a> · <a href="https://github.com/aHappend/hammer-v">Hammer-V</a> · <a href="https://github.com/aHappend/rivet-a">Rivet-A</a> · <a href="https://github.com/aHappend/rivet-h">Rivet-H</a> · <a href="https://github.com/aHappend/swage-s">Swage-S</a> · <a href="https://github.com/aHappend/sable">SABLE</a> · <a href="README.md"><strong>English</strong></a>
  </p>
</div>

---

**Billet-T** 是 Vulcan 芯片舰队的频域信号处理产品线，包含已完成全壳四角静态时序收敛与物理板卡实测的 256 点复数基 2 FFT 加速芯片（`BILLET-T1`）。

## Vulcan 3.0 全壳物理硅片签核总表

`chips/` 目录下的芯片均在 **完整 Intel Arria 10 GX PCIe Gen3x8 + DDR4-2133 平台外壳**（`10AX115N3F40E2SG`，Quartus Prime Standard `17.1.0`）内完成布局布线与四角静态时序闭合，并通过物理板卡真机上板逐字节验证（`board_hil`）及同口径 `AMD EPYC 7662` CPU 与 `NVIDIA Tesla V100` GPU 基准测试。

| 代际 | 芯片代号 | 微架构与工程验证范围 | 全壳四角静态时序（STA） | 含外壳整芯片资源占用 | 物理板卡上板（HIL） | 公开工程交付物 |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **Gen-1 (v3.0)** | [**BILLET-T1**](chips/billet-t1/README.zh-CN.md) | 256 点定点基 2 复数快速傅里叶变换（FFT）芯片 · 乒乓帧缓存 SRAM、位反转寻址与旋转因子蝶形流水线 | **`132.96 MHz`**（`WNS +2.479 ns`）<br><sub>PCIe `278.24` · DDR4 `276.78 MHz`</sub> | `42,670 ALMs (10 %)`<br><sub>`3 DSPs` · `189 M20K`</sub> | **实测通过**<br><sub>PCIe Gen3x8 + DDR4</sub> | [**`REPORT.pdf`**](chips/billet-t1/REPORT.pdf) · [RTL](chips/billet-t1/rtl/) · [凭证](chips/billet-t1/evidence/) |

## 工程签核报告图文预览

### BILLET-T1 · Vulcan 3.0 工程签核报告图文预览（[`chips/billet-t1/REPORT.pdf`](chips/billet-t1/REPORT.pdf)）
<table>
  <tr>
    <td align="center" width="33%"><a href="chips/billet-t1/REPORT.pdf"><img src="chips/billet-t1/report_preview/page-1.png" width="100%" alt="BILLET-T1 第 1 页"></a><br><sub><strong>第 1 页 · 芯片定位与微架构总览</strong></sub></td>
    <td align="center" width="33%"><a href="chips/billet-t1/REPORT.pdf"><img src="chips/billet-t1/report_preview/page-2.png" width="100%" alt="BILLET-T1 第 2 页"></a><br><sub><strong>第 2 页 · 数据通路设计与验证矩阵</strong></sub></td>
    <td align="center" width="33%"><a href="chips/billet-t1/REPORT.pdf"><img src="chips/billet-t1/report_preview/page-3.png" width="100%" alt="BILLET-T1 第 3 页"></a><br><sub><strong>第 3 页 · 全壳时序、上板实测与基准对比</strong></sub></td>
  </tr>
</table>

## 仓库目录结构

```text
billet-t/
├── README.md               # 正式英文技术文档
├── README.zh-CN.md         # 正式简体中文技术文档
├── brand/                  # 浅色/深色自适应矢量品牌标识
├── chips/
│   ├── billet-t1/             # BILLET-T1（RTL、测试、STA/HIL 凭证与工程报告）
├── archive-v2/             # 3.0 之前历史探索版本归档
└── LICENSE                 # MIT 开源协议
```

---
<p align="center"><sub>作者：<strong>郭苏峰（Sufeng Guo）</strong> · <a href="https://github.com/aHappend/vulcan-showcase">Vulcan 硅片成果总览</a> · <a href="LICENSE">MIT 开源协议</a></sub></p>
