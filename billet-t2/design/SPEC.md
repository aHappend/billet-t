# BILLET-T2: runtime-configurable FFT/IFFT RTL IP

## Scope and source continuity

BILLET-T2 is a single iterative radix-2 DIT engine for N=16,32,64,128,256.
It extends BILLET-T1 with runtime length, conjugated-twiddle inverse operation,
programmable stage scaling and frame-wide block floating-point normalization.
`rtl/billet_t2_top.sv` is the fixed, parameterless public top.
All five `rtl/*.sv` files are required delivery sources.
`billet_t1_reference/rtl/*.sv` remains unchanged compatibility provenance and
is an independent verification input, not the T2 datapath.

Bit-exact compatibility is required for N=256, forward FFT, fixed stage scaling:
every component, bin index and cumulative saturation diagnostic must agree with
the actually simulated mounted T1. Latency is intentionally different.
Reference inspection is not a passing reference baseline.

## Public ports

All ports below are fixed; no debug/benchmark or parameter interface is exposed.

| Direction | Ports | Contract |
| --- | --- | --- |
| Input | `clk`, `rst_n` | Rising-edge clock, asynchronous active-low reset. |
| Input | `in_valid`, `in_last` | Input valid and advisory last marker. |
| Input | signed `in_re[15:0]`, `in_im[15:0]` | Natural-order signed Q1.15 sample integer codes. |
| Input | `cfg_log2_n[3:0]` | Legal values 4..8. |
| Input | `cfg_ifft` | 0 forward FFT, 1 unnormalized inverse with conjugated forward constants. |
| Input | `cfg_scale_mode[1:0]` | 0 fixed shift, 1 stage mask, 2 BFP; 3 illegal. |
| Input | `cfg_stage_shift_mask[7:0]` | Bit s selects a one-bit right shift at active stage s in mode 1. |
| Input | `out_ready` | Consumer accepts an output on valid/ready. |
| Output | `in_ready`, `out_valid`, `out_last` | Transfer controls; last only accompanies valid bin N-1. |
| Output | signed `out_re[15:0]`, `out_im[15:0]` | Natural-order transform bins. |
| Output | `out_bin_idx[7:0]` | Bin 0..N-1, no gaps or duplication. |
| Output | `out_block_exp[3:0]` | Total actual stage shifts, same on every output in a frame. |
| Output | `frame_done` | One-cycle pulse immediately following the last output handshake. |
| Output | `cfg_error` | Invalid live configuration only while idle and out of reset. |
| Output | `overflow_flag`, `saturation_count[31:0]` | Reset-only sticky overflow, saturating cumulative number of clamped real/imaginary components. |

## Frame protocol and reset

Transfer means rising edge with valid and ready both high. Configuration latches
only on the first accepted input. Ignore all subsequent live config changes
through the last output acceptance, including changes during loading. Exactly N
accepted inputs form a frame. `in_last` is advisory: early, absent or late
markers neither truncate nor extend the frame, preserving T1 count-based framing.
Only one frame is live; no overlap is accepted.

Idle invalid configuration asserts `cfg_error` and deasserts ready without
accepting a sample. During an active frame error is zero. No separate config
handshake exists. On reset every public output is zero, including ready,
payload, diagnostics and exponent. Reset aborts any loading, processing or
output frame. After release idle ready immediately reflects legal live config.
Unreset memories are safe because each consumed location is written by the
current frame before consumption.

While valid is stalled, all payload and metadata remain stable, including bin,
last and exponent. When valid is zero, real, imaginary, bin, last and exponent
are zero. Diagnostic counters, error and done retain their separate meanings.
The last output handshake returns to idle; another frame may begin on the
following edge. The cycle table and exact no-stall schedule are specified in
[ARCHITECTURE.md](ARCHITECTURE.md).

## Arithmetic and scaling

Load using exactly log2(N)-bit reversal; process stages s=0..log2(N)-1.
At stage s, use canonical 256-grid address `j << (7-s)`, equivalent to the
selected-N twiddle index times 256/N. Forward constants are copied exactly
from T1: quantized Q1.15, +1=32767 and -1=-32768. Inverse conjugation uses signed
17-bit twiddles so -32768 negates exactly to +32768.

Individual products are signed 33-bit, combined complex products signed 34-bit.
Arithmetic-shift each combined product by 15, then add/subtract signed a in
35 bits. Store lossless signed 18-bit unscaled raw components. No rounding
to nearest and no clipping before normalization. Right shift floors negative
values. Only after the selected stage shift clamp each component to
[-32768,32767].

Mode 0 shifts every stage by one. Mode 1 shifts iff the corresponding active
mask bit is one; inactive upper bits have no effect. Mode 2 observes all N
complex raw outputs of the entire stage and shifts that whole stage exactly
once iff any real/imaginary component is outside [-32768,32767]. Signed range
comparisons avoid absolute-value overflow at -32768. There is no hidden extra
shift: arbitrary full-scale complex inputs may still saturate after one shift.

The block exponent E counts actual shifts in **all** modes, from zero each
frame. The result represents approximately FFT(x)/2^E or unnormalized
IFFT(x)/2^E. There is no implicit inverse 1/N factor; mode 0 supplies it through
log2(N) shifts. To compare spectra on the original scale multiply integer
outputs by 2^E, accounting for Q1.15 units where applicable.

Count each clamped component only when its normalized sample is written.
Wide excursions made representable by scaling are not saturation events.
Not-yet-normalized work abandoned by reset does not count. The cumulative
counter saturates at 0xffffffff, never wraps; any count increment sets overflow.
Only reset clears these two diagnostics.

## Reproducibility, acceptance and limitations

Prerequisites are Python 3 with only its standard library, Icarus Verilog
(`iverilog -g2012`) plus `vvp`, and Yosys with a supported SystemVerilog frontend.
No installation is part of this work order. Record actual versions in retained
execution evidence; tool portability is not assumed from source inspection.
Top-only static elaboration from the delivered root can use:

```sh
iverilog -g2012 -t null -s billet_t2_top rtl/*.sv
```

The independent Verifier owns and supplies these acceptance entrypoints:

```sh
python3 tests/verify.py --check behavior --output-dir evidence/verification/behavior
python3 tests/verify.py --check synthesis --output-dir evidence/verification/synthesis
```

The behavior claim requires real RTL simulation, exact independent integer
scoreboarding, independently generated mathematical twiddles, direct O(N^2)
DFT/IDFT orientation checks and direct simulation of unchanged T1. Cover all
length/direction/mode combinations, mask boundaries, seeded and directed
arithmetic, invalid config, config changes while busy, stalls, reset in every
phase and exact cycle timing. A deliberately incorrect private example must
demonstrate scoreboard defect detection. Unknown active outputs, malformed
input, assertion failures, child failures and timeouts must fail the entrypoint.

For each N, at least three fixed seeded low-amplitude frames (components in
[-64,64]) must reconstruct through RTL forward mode 1/mask 0 then inverse
mode 0 without saturation: maximum component error <=32 input LSB and
complex-sample RMS error <=8 input LSB. For positive real impulse amplitude
64, require BFP E=0, fixed E=log2(N), and strictly lower aggregate squared
exponent-rescaled BFP spectral error versus the independent mathematical FFT.
Also report seeded low-amplitude comparisons without claiming universal BFP
improvement. Exact oracle equality remains mandatory.

Generic synthesis must retain substantive arithmetic, sequential and storage
logic, with no latches, unresolved modules or black boxes, using hierarchy,
process/memory lowering, optimization and consistency checks. Retain actual
commands, versions, statistics and netlist. Simulation/synthesis subprocess
wall limits are at least 3600 seconds with finite logical simulation watchdogs.

Claim evidence belongs under
[`evidence/verification/behavior/`](../evidence/verification/behavior/) and
[`evidence/verification/synthesis/`](../evidence/verification/synthesis/).
These are intended destinations, **not asserted passing or existing results at
Designer handoff**. Numerical measurements and engineering acceptance remain
pending independent verification and review. No physical process, target FPGA,
clock frequency, area, power, timing closure, deployment or manufacturing
sign-off is claimed. Logical banks do not promise a particular memory macro.
The later runtime-authored product report is not a verification prerequisite.
