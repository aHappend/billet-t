# Billet-T — Repository guide / 文件导航

[English](README.md) · [简体中文](README.zh-CN.md)

Documentation inventory checked on 2026-11-17, against repository base `0661f2f26ddbe3394a2d2378cab623afdcd5c654`.

## Reading the inventory / 阅读方法

This is a path-level index, not a new experiment or a recertification. Each measurement belongs to the exact linked record and directory. Different copies of a chip can contain different source revisions and results. A recorded pass does not imply that another copy, model size, software stack or board image passed.

本页按实际路径列出交付物，不代表新实验或重新签核。同名芯片的多份目录可能有不同源码和结果；一份记录的通过不外推到其他副本、模型规模、软件栈或板卡镜像。

## Source, tests and reports / 源码、测试与报告

| Existing directory | Source / constraints | Public tests / technical documents | Reports |
| --- | --- | --- | --- |
| [`billet-t1/`](billet-t1/) | [`billet-t1/rtl/`](billet-t1/rtl/) | [`billet-t1/tests/`](billet-t1/tests/) · [`billet-t1/design/`](billet-t1/design/) · [`billet-t1/README.md`](billet-t1/README.md) | [`billet-t1/REPORT.md`](billet-t1/REPORT.md) · [`billet-t1/REPORT.pdf`](billet-t1/REPORT.pdf) · [`billet-t1/SHOWCASE_REPORT.pdf`](billet-t1/SHOWCASE_REPORT.pdf) · [`billet-t1/SHOWCASE_REPORT.zh-CN.pdf`](billet-t1/SHOWCASE_REPORT.zh-CN.pdf) |
| [`billet-t2/`](billet-t2/) | [`billet-t2/rtl/`](billet-t2/rtl/) | [`billet-t2/tests/`](billet-t2/tests/) · [`billet-t2/design/`](billet-t2/design/) · [`billet-t2/README.md`](billet-t2/README.md) | [`billet-t2/REPORT.md`](billet-t2/REPORT.md) · [`billet-t2/REPORT.pdf`](billet-t2/REPORT.pdf) · [`billet-t2/SHOWCASE_REPORT.pdf`](billet-t2/SHOWCASE_REPORT.pdf) · [`billet-t2/SHOWCASE_REPORT.zh-CN.pdf`](billet-t2/SHOWCASE_REPORT.zh-CN.pdf) |
| [`billet-t3/`](billet-t3/) | [`billet-t3/rtl/`](billet-t3/rtl/) | [`billet-t3/tests/`](billet-t3/tests/) · [`billet-t3/design/`](billet-t3/design/) · [`billet-t3/README.md`](billet-t3/README.md) | [`billet-t3/REPORT.md`](billet-t3/REPORT.md) · [`billet-t3/REPORT.pdf`](billet-t3/REPORT.pdf) · [`billet-t3/SHOWCASE_REPORT.pdf`](billet-t3/SHOWCASE_REPORT.pdf) · [`billet-t3/SHOWCASE_REPORT.zh-CN.pdf`](billet-t3/SHOWCASE_REPORT.zh-CN.pdf) |

## Public result records / 公开结果记录

Status and numbers below are transcribed only from the linked record. Functional simulation, generic synthesis, standalone/virtual-pin timing, bridge connectivity, workload readback and system-software execution are separate scopes. Missing entries mean that this index found no matching public record at that path, not that an experiment failed or never occurred.

下表状态与数值只来自对应文件。功能仿真、通用综合、独立 IP／虚拟引脚时序、桥接连通性、工作负载读回和系统软件执行分别解释；未列出不等于判定失败或从未做过。

| Exact directory | Record | Recorded result and scope |
| --- | --- | --- |
| `billet-t1` | [`billet-t1/STATUS.json`](billet-t1/STATUS.json) | recorded engineering acceptance: `true` |
| `billet-t2` | [`billet-t2/STATUS.json`](billet-t2/STATUS.json) | recorded engineering acceptance: `true` |
| `billet-t3` | [`billet-t3/STATUS.json`](billet-t3/STATUS.json) | recorded engineering acceptance: `true` |

## File-management policy / 文件管理约定

- Keep RTL, constraints, tests and result originals in their existing locations. This documentation refresh does not move or delete them.
- Hyphenated, underscored and `chips/` directories are separate existing trees, not interchangeable aliases. The index lists all of them without declaring one authoritative.
- Preserve dated reports as publications. Update the README and this guide when the public source/evidence changes; do not silently rewrite an old result.
- Keep chip artifacts separate from the private Vulcan implementation. Public reproducibility instructions must not require private framework code or internal operation traces.

保留现有源码、约束、测试和原始证据路径；连字符、下划线和 `chips/` 多份目录不自动视为等价。历史报告保留其发表时范围，公开复现不得依赖私有框架实现。
