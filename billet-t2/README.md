# BILLET-T2

Configurable FFT/IFFT lengths and scaling.

**Status:** Engineering accepted.

## Reproduce

Requires Python 3, Icarus Verilog (`iverilog`, `vvp`) and Yosys.
Run from this generation's directory:

```bash
python3 tests/verify.py
```

The test driver creates fresh local evidence. A published status is not a new run on your machine.

[Specification](design/SPEC.md) · [Architecture](design/ARCHITECTURE.md) · [RTL](rtl/) · [Verification source](tests/) · [Recorded check statuses](STATUS.json)

The independently reviewed product report has not been published yet.

Simulation and generic synthesis do not establish physical signoff or measured silicon performance.
