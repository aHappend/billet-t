<p align="center"><picture><source media="(prefers-color-scheme: dark)" srcset="brand/logo-dark.svg"><img src="brand/logo.svg" width="480" alt="Vulcan"></picture></p>

<h1 align="center">BILLET-T · Signal-processing silicon, forged with Vulcan.</h1>

[Vulcan](https://ahappend.github.io/vulcan/) · [Showcase](https://github.com/aHappend/vulcan-showcase) · [Anvil-E](https://github.com/aHappend/anvil-e) · [RIVET-A](https://github.com/aHappend/rivet-a) · [BILLET-T](https://github.com/aHappend/billet-t)

[English](README.md)

**信号处理芯片家族 · 频域变换产品线**。BILLET 是独立家族，BILLET-T 是其中的产品线，不隶属于 Anvil。

## 代际路线与实际状态

| Generation | Design | Scope | Engineering status | Product report |
|---|---|---|---|---|
| 1 | [BILLET-T1](billet-t1/) | 256-point fixed-point complex FFT with explicit numeric and buffer rules | Engineering accepted | [PDF](billet-t1/REPORT.pdf) |
| 2 | [BILLET-T2](billet-t2/) | Configurable FFT/IFFT lengths and scaling | Engineering accepted | Pending |
| 3 | [BILLET-T3](billet-t3/) | Multichannel windowing, overlap processing and power spectra | Not accepted (planning) | Pending |

`Engineering accepted` 表示原生工程验收已通过；`Not accepted` 表示尚未验收；`Pending` 表示报告尚未发布。规划不算成果，后续代际不覆盖前代目录。

验收后发布规格、RTL、可执行验证程序；报告在实际渲染产物获批后追加。各代目录含复现命令和精简检查状态，不发布账号、模型对话、私有经验、框架状态或内部原始日志。报告中的内部相对证据路径仅作溯源，相关内部文件不随公开包提供；用户可运行验证程序生成自己的证据。

当前结果不等于流片、实测 PPA、侧信道认证或板级实时性能。发布流程见 [PUBLISHING.md](PUBLISHING.md)。

## 许可证

[MIT](LICENSE)，与 Anvil 成果仓库一致。
