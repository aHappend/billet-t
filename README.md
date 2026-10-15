<p align="center"><picture><source media="(prefers-color-scheme: dark)" srcset="brand/logo-dark.svg"><img src="brand/logo.svg" width="480" alt="Vulcan"></picture></p>

<h1 align="center">BILLET-T · Signal-processing silicon, forged with Vulcan.</h1>

[Vulcan](https://ahappend.github.io/vulcan/) · [Showcase](https://github.com/aHappend/vulcan-showcase) · [Anvil-E](https://github.com/aHappend/anvil-e) · [RIVET-A](https://github.com/aHappend/rivet-a) · [BILLET-T](https://github.com/aHappend/billet-t)

[中文](README.zh-CN.md)

**BILLET** is an independent silicon family. **BILLET-T** is its current series.
This repository publishes selected open engineering deliverables produced with Vulcan.

## Series roadmap

| Generation | Design | Scope | Engineering status | Product report |
|---|---|---|---|---|
| 1 | [BILLET-T1](billet-t1/) | 256-point fixed-point complex FFT with explicit numeric and buffer rules | Engineering accepted | [PDF](billet-t1/REPORT.pdf) |
| 2 | [BILLET-T2](billet-t2/) | Configurable FFT/IFFT lengths and scaling | Not accepted (checks) | Pending |
| 3 | [BILLET-T3](billet-t3/) | Multichannel windowing, overlap processing and power spectra | Not accepted (planned) | Pending |

Accepted sources are published separately from in-progress status. Each generation keeps its own specification, RTL, executable verification and report. Planned generations are not completed products.

## Publication and scope

Only selected product files and a compact check-status record are exported. Accounts, model sessions, private experience, framework state and raw internal logs are excluded. Reports are published only after rendered-artifact approval. Internal relative evidence references in reports are provenance, not links to files included in this public package; regenerate public test evidence with the command above.

No tapeout, measured PPA, side-channel certification or board-level performance is claimed.

## License

[MIT](LICENSE), consistent with the Anvil results repositories.
