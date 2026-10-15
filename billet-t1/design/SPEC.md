# BILLET-T1 numerical and integration specification

## Scope and configuration

BILLET-T1 is a serialized, radix-2, forward complex FFT RTL IP with nominal
1/N normalization. The top is `billet_t1_top`. `N_POINTS` defaults to 256;
supported values are powers of two from 2 through 256. `LOG2_N` is derived as
`$clog2(N_POINTS)` and must not be overridden inconsistently. Address width
`A=max(1,LOG2_N)` and stage width `S=max(1,$clog2(LOG2_N))`. Illegal sizes,
including 0, 1, negative, non-power-of-two and above 256, produce an explicit
simulation `$fatal` parameter diagnostic. Guarded dimensions and generate
branches allow that diagnostic to execute. This is not support for those sizes.

The deliverable is synthesizable technology-independent RTL, not a physical
chip implementation, SRAM macro binding, timing closure or measured PPA result.

## Public interface

All signals use one `clk`. Sequential control and datapath registers have
asynchronous active-low `rst_n`; sample memories are not reset.

| Direction | Signals | Meaning |
| --- | --- | --- |
| Input | `clk`, `rst_n` | Clock and asynchronous reset |
| Input | `in_valid`, `in_last` | Input offer and expected final-beat marker |
| Input | signed `[15:0] in_re,in_im` | Complex Q1.15 sample |
| Output | `in_ready` | Engine can accept one sample |
| Input | `out_ready` | Consumer accepts offered output |
| Output | `out_valid`, `out_last` | Output offer and final-bin indicator |
| Output | signed `[15:0] out_re,out_im` | Complex Q1.15 FFT result |
| Output | `[A-1:0] out_bin_idx` | Natural-order frequency bin |
| Output | `frame_done` | One-cycle completion after final output acceptance |
| Output | `overflow_flag` | Sticky indication of any component clamp |
| Output | `[31:0] saturation_count` | Sticky, saturating component-clamp counter |

A transfer occurs only at a rising edge with valid and ready both asserted
before the edge. Exactly N accepted natural-order input samples form a frame.
`in_last` is advisory: early or missing markers do not truncate, pad, restart
or change a fixed-length transform. It has no datapath or state effect.
Input gaps are legal. The engine deasserts `in_ready` during computation and
output, and processes one frame at a time. A source can continuously offer the
next frame, holding each unaccepted beat stable. There is no inter-frame overlap.

During reset every public output is zero, including ready, valid and telemetry.
After reset release, LOAD is ready, including before the first rising edge.
Reset aborts partial load, computation or output without a completion pulse.
A full subsequent frame initializes all storage locations used by its transform.
When `out_valid=0`, output data, index and last are zero. A valid stalled
payload, index and last remain unchanged until acceptance or reset.

## Deterministic arithmetic

All sample and coefficient codes are signed integers representing code/32768.
For `k=0..N/2-1`, the ROM provides

```
W_re[k] = clamp16(round_half_away_from_zero(32768*cos(2*pi*k/N)))
W_im[k] = clamp16(round_half_away_from_zero(-32768*sin(2*pi*k/N)))
```

`clamp16(x)=min(32767,max(-32768,x))`. In particular +1 maps to 32767,
and -1 maps to -32768. The literal 256-point half-circle table is addressed
by `k*(256/N)`. There are no real-number calculations in RTL.

Each combinational butterfly uses four exact signed 16x16-to-32-bit products.
Sign extension precedes the following signed 33-bit sums:

```
P_re = B_re*W_re - B_im*W_im
P_im = B_re*W_im + B_im*W_re
T_c  = floor(P_c/32768)          // signed >>> 15, kept at 33 bits
U_c  = floor((A_c + T_c)/2)      // 34-bit sum, signed >>> 1
V_c  = floor((A_c - T_c)/2)      // 34-bit difference, signed >>> 1
Y0_c = clamp16(U_c)
Y1_c = clamp16(V_c)
```

There is no rounding bias, premature 16-bit narrowing, pre-scaling clamp,
optional scaling or arithmetic wraparound. Quantization rounds toward negative
infinity at both shifts. Nominal scaling is 1/N across all LOG2_N stages.
`sat_inc` counts the 0..4 scalar components changed by the final clamps.
On every committed butterfly, that value is added to `saturation_count`,
saturating at `32'hffffffff`; `overflow_flag` sets if it is nonzero.
Both are reset-cleared, remain sticky across frames and do not change merely
because an output is stalled.

Division by two bounds ordinary butterfly adder growth, but cannot guarantee
zero component clipping for arbitrary independently full-scale complex inputs.
A rotated square-domain sample can exceed a component rail. For example,
the legal N=16 input with n=0,2 equal to (-32768,-32768), n=8,10 equal to
(32767,32767), n=4,6 equal to (32767,-32768), n=12,14 equal to
(-32768,32767), and odd samples zero, produces, after stages 0 and 1,
operands (-32767,-32767) in each of positions 1 and 5. At stage 2, j=1,
W=(23170,-23170) rotates the latter to T=(-46339,0). Thus the real U is
floor((-32767-46339)/2)=-39553 and clamps to -32768. This is intentional
clipping, not intermediate overflow. Independent verification must calculate
all clamp events, retain arbitrary-full-scale stress, and separately establish
zero saturation for rail-safe quality cases.

## Cycle and degenerate-boundary table

Let F accept the final input beat and C=N*LOG2_N. Handshakes are sampled
pre-edge; the table describes state and outputs after each named edge.

| Edge or condition | Post-edge behavior |
| --- | --- |
| Reset asserted, regardless of clock | All public outputs zero; transaction aborted |
| Reset released | LOAD ready; no valid output or completion |
| Nonfinal accepted input | Accepted-input count advances once |
| F | LOAD ends, ready goes low, first READ selected |
| F+1 | First operand pair captured; WRITE selected |
| F+2 | First butterfly committed; next READ or stage selected |
| F+C | Final butterfly committed; final bank selected; FETCH selected |
| F+C+1 | Bin 0 holding register loaded; valid becomes 1 |
| F+C+2 | Earliest bin-0 handshake |
| SEND edge H, ready=0 | Valid payload/index/last held unchanged |
| SEND edge H, accepted nonfinal bin | Valid goes low; next FETCH selected |
| H+1 | Next bin fetched; valid becomes 1 |
| H+2 | Earliest next-bin handshake |
| D, final output handshake | Valid goes low, done becomes 1, LOAD ready |
| D+1 | Done clears; next frame's first beat may be accepted |
| N=2 | One READ/WRITE butterfly; final bank 1; same FETCH/SEND rules |
| Illegal N or inconsistent LOG2_N | Explicit parameter diagnostic, inert datapath |

With no output stalls, `D=F+C+2*N`. With no input bubbles, the first input
acceptance to final output acceptance distance is `N-1+C+2*N` edges.
There is one FETCH bubble between accepted output beats. Reset has priority
over every handshake, completion and telemetry increment. LOAD, READ, WRITE,
FETCH and SEND are mutually exclusive: there is no simultaneous memory
read/write in a bank and no simultaneous load and butterfly commit.

## Source order and tool entry points

Compile from the delivered root, package first:

```
iverilog -g2012 -t null -s billet_t1_top \
  rtl/billet_t1_pkg.sv rtl/billet_t1_twiddle_rom.sv \
  rtl/billet_t1_bitrev.sv rtl/billet_t1_butterfly.sv \
  rtl/billet_t1_buffer_sched.sv rtl/billet_t1_top.sv
```

For example, append `-Pbillet_t1_top.N_POINTS=16` for the 16-point variant.
The independent Verifier owns `tests/*.py`, including `tests/verify.py`;
the intended complete acceptance invocation is `python3 tests/verify.py`.
Targeted admitted entries are `--check behavior`, `--check mutations` and
`--check synthesis`. Dependencies are Python 3 standard library, Icarus
(`iverilog`, `vvp`) and Yosys. Their availability and versions, functional
results, numerical quality, mutation sensitivity and synthesis results must be
recorded by independent verification; this document does not claim those pass.
