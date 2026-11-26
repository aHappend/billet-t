# BILLET-T3 specification

## Scope and fixed boundaries

BILLET-T3 is a four-channel, time-multiplexed spectral processing engine.
It supports complex FFT/IFFT lengths N=16,32,64,128,256, programmable stage
scaling and block floating point (BFP). Each channel assembles continuous raw
samples into non-overlapping or 50%-overlapping analysis frames. There is one
serial transform engine. The design adds no synthesis-side overlap accumulator,
filter kernel, reconstruction stream or implicit IFFT normalization.

The delivered top is `billet_t3_top` in `rtl/billet_t3_top.sv`. Compile all
`rtl/*.sv`; the mounted `billet_t2_reference/rtl/*.sv` are continuity references,
not dependencies of the delivered hardware. There are no public structural
parameters, DEPTH or MAX_WORDS. N=1 and non-power-of-two lengths are unsupported:
length is encoded exclusively by the legal log2 values below.

## Top ports

All ports are unsigned unless explicitly marked signed. All inputs are sampled
on the rising clock edge except asynchronous active-low reset.

| Direction | Ports | Width and meaning |
|---|---|---|
| input | clk, rst_n | 1 each; clock and asynchronous active-low reset |
| input | in_valid, in_last | 1 each; offered sample, informational legacy last |
| input | in_re, in_im | signed 16 each; raw complex sample |
| input | ch_id | 2; offered channel 0..3 |
| input | cfg_log2_n | 4; legal 4..8 |
| input | cfg_ifft | 1; 0 FFT, 1 IFFT |
| input | cfg_scale_mode | 2; 0 shift every stage, 1 mask, 2 BFP, 3 invalid |
| input | cfg_stage_shift_mask | 8; bit s selects a right shift at stage s |
| input | cfg_overlap_mode | 1; 0 hop N, 1 hop N/2 |
| input | cfg_window_mode | 2; 0 rectangular, 1 Hann, 2 Hamming, 3 invalid |
| input | out_ready | 1; downstream accepts offered output |
| output | in_ready | 1; offered channel can accept a sample |
| output | cfg_error | 1; invalid configuration when offered channel needs capture |
| output | out_valid, out_last | 1 each; valid bin, final bin |
| output | out_re, out_im | signed 16 each; post-scaling, saturated complex bin |
| output | out_power | 32; exact unsigned sum of output component squares |
| output | out_bin_idx | 8; natural-order bin 0..N-1 |
| output | out_block_exp | 4; number of stage shifts, 0..log2(N) |
| output | out_ch_id | 2; active output frame's channel |
| output | frame_done, frame_done_ch_id | 1, 2; completion pulse and its channel |
| output | overflow_flag | 1; sticky component saturation since reset |
| output | saturation_count | 32; cumulative component saturations, saturating counter |

## Configuration epochs and acceptance

An input transfer occurs only on `in_valid && in_ready`. `in_last` is ignored,
as in Gen-2; accepted counts alone delimit frames. A channel captures **all**
configuration fields on its first accepted sample in an epoch. Pins describe
only the currently offered channel. Once captured, changing pins (even to
invalid settings) cannot block or alter the rest of that epoch.

Before capture, log2 outside 4..8, scale mode 3 or window mode 3 asserts
`cfg_error` independently of `in_valid`, deasserts `in_ready`, and changes no
sample/configuration state. Errors are not sticky. Reset suppresses cfg_error.
A reserved non-overlap channel has already ended its epoch, so invalid offered
configuration can assert cfg_error even though its old frame remains pending.

A non-overlap epoch ends on its Nth accepted sample; a new configurable epoch
can begin after its ring reservation has been released. An overlap epoch and
its configuration persist until reset. Live reconfiguration of overlapping
history is not supported. Other channels remain independently configurable.

## Rings, frames and fairness

There are four raw complex rings, each physically 256 words, wrapping at the
captured N. Before N accepted samples there is no frame. Non-overlap frame m
contains samples m*N through m*N+N-1. Overlap frame m contains samples
m*(N/2) through m*(N/2)+N-1. The first frame requires N samples; subsequent
overlap frames require exactly N/2 new samples. Repeated ring wraps do not
change chronological frame order.

One complete-frame reservation per channel prevents writes to that channel
until all N chronological beats transfer to the transform core. Other eligible
channels can accept samples during that reservation, computation or output
stall. On release, overlap retains the newest N/2 raw samples; non-overlap
releases all history. There is no same-edge replacement of a reservation.

Complete frames are selected in round-robin order, initially starting with
channel 0. Selection is registered; a frame's transfer is contiguous. On its
final transfer, priority starts at the following channel. Selection may reserve
the next frame while the core is busy, but cannot change a stalled frame's
payload. With eventual output readiness, continuously pending channels cannot
starve. Output order is selection order, not global input-arrival order.

## Window and integer arithmetic

Rectangular mode is an exact bypass. For n=0..N-1:

* Hann: w[n] = 0.5 - 0.5*cos(2*pi*n/(N-1)).
* Hamming: w[n] = 0.54 - 0.46*cos(2*pi*n/(N-1)).
* q[n] = min(32767, floor(32768*w[n] + 0.5)).

The RTL embeds precomputed constants for all five lengths, stores only each
first half, and mirrors indices exactly. Coefficients are nonnegative signed
16-bit Q1.15. Each component uses a full signed 32-bit product followed by an
arithmetic right shift of 15 (truncate toward negative infinity). No window
saturation is needed. Raw history is windowed anew at each frame position,
before bit-reversed transform storage. The window is combinational.

The radix-2 DIT core preserves the mounted Gen-2 twiddle table bit-for-bit.
The positive-unity approximation is 32767 and negative unity is -32768.
External twiddles are signed 17-bit; IFFT negates the sign-extended forward
imaginary coefficient so +32768 is representable. Signed 16x17 products have
33 bits, complex product sums/differences 34 bits; shift right 15 occurs only
after that sum/difference. Butterfly results are signed 18-bit.

Each whole stage is observed before normalization. Mode 0 shifts all samples
once; mode 1 uses that stage's mask bit; BFP shifts once iff any raw component
is outside [-32768,32767]. After the arithmetic shift, clamp components to
signed 16-bit range. BFP may still saturate an extreme raw result after its
single shift. The block exponent counts stage shifts, not saturations.
Saturation increments the global count per real/imaginary component and sets
sticky overflow. The count saturates at 0xffffffff. Neither windows nor power
contribute to it. IFFT has no additional normalization.

Power is combinational and exact: unsigned P = Re^2 + Im^2, maximum 0x80000000
at (-32768,-32768). It describes the delivered integer bin, without exponent
compensation; physical-scale unsaturated power additionally has factor
2^(2*out_block_exp).

## Cycle & degenerate-boundary table

Handshakes use **pre-edge** values; "after" means after nonblocking updates.
The window and power units add no registered cycles.

| Event / boundary | Pre-edge condition | Post-edge behavior |
|---|---|---|
| asynchronous reset assertion | rst_n falls, no clock needed | Every public output is zero; all control, histories' validity, tags, flags and counters clear; memories need not clear |
| first clock after release | no accepted input yet | Empty valid state persists; ready reflects offered legal configuration; no old output |
| sample edge E | in_valid && in_ready | Exactly one raw sample stored; completing frame becomes pending only after E |
| registered selection E+1 or later | an already pending frame exists, no active selection | First f_valid may assert; a reservation created on E cannot transfer on E |
| frame beat | f_valid && f_ready | Pre-edge chronological sample is windowed and stored at bit-reversed address |
| final frame beat F | f_last && f_valid && f_ready | Core enters BUTTERFLY_READ; reservation releases, priority advances; blocked channel becomes eligible only afterward |
| computation | N/2 butterflies per stage, 2 cycles each; N normalization samples, 2 cycles each | First out_valid immediately after F + 3*N*log2(N) + 1 |
| output stall | out_valid && !out_ready | All payload, exponent, tag and last remain unchanged |
| nonfinal output edge O | out_valid && out_ready && !out_last | Fetch state; next bin becomes valid after O+1, first transferable at O+2 |
| final output edge L | out_valid && out_ready && out_last | Core LOAD; frame_done=1 and completed tag; no new frame beat consumed on L |
| edge L+1 | completion was high | frame_done=0 and done tag zero unless another completion (impossible at supported lengths) |
| simultaneous input and frame transfer | different unreserved offered channel | Independent ring write and transfer; reserved channel cannot write on release edge |
| reset with pending/partial/stalled frame | any state | Reset dominates all transfers; no pre-reset result survives |
| N=16 / N=256 | legal log2=4 / 8 | Same schedule; 9-bit counts represent full N=256 |
| N-1 / N accepted samples | empty epoch | No frame / exactly first reservation |
| N+H-1 / N+H accepted samples | reservation released, overlap H=N/2 | No second frame / second reservation |
| channel 0 / 3 and all four pending | any legal lengths | Fixed 2-bit tags; round-robin wraps 3 to 0 |
| DEPTH=1, MAX_WORDS=1, non-power-of-two | no such parameters | Not structural configurations of this IP; illegal length encodings rejected |

All inactive output payload, tag, exponent, index and last fields are zero.
frame_done_ch_id is zero unless frame_done is high. Status remains visible
outside valid output cycles, except all outputs are zero during reset.

## Verification entry points and claim-to-check index

Independent Verifier owns `tests/*.py`, including `tests/verify.py`; these
commands are the admitted entry points, not a statement that checks have passed:

```
python3 tests/verify.py --check behavior --output evidence/behavior
python3 tests/verify.py --check synthesis --output evidence/synthesis
python3 tests/verify.py --check delivery --output evidence/delivery
```

Prerequisites: Python 3 standard library, Icarus `iverilog` with SystemVerilog
(`-g2012`), `vvp`, and Yosys with SystemVerilog support. Actual versions and
availability must be recorded by execution, not inferred here. No Python
numerical package, downloaded tool or private runtime metadata is required.
Generated bridges, compiled binaries, logs and netlists belong under evidence
build/output directories, never in source selectors.

For a static top-level syntax/elaboration check only:
`iverilog -g2012 -s billet_t3_top -t null rtl/*.sv`.
This is not functional or synthesis acceptance.

| Claim | Independent check |
|---|---|
| FFT/IFFT arithmetic, all lengths/scaling, exact windows and power | behavior: independent integer oracle, separate mathematical DFT and Gen-2 differential comparison |
| Channel isolation, overlap chronology, count boundaries, repeated wrap, fair arbitration | behavior: accepted-beat stream scoreboards and public boundary witnesses |
| Reset, invalid settings, stalls, exact latency, final beat/done | behavior: cycle-level public-interface checks, active X/Z rejection |
| Reachable required hierarchy, real hardware, no latches | synthesis: real Yosys elaboration and synthesis |
| Complete source package, commands, hierarchy, docs, scoreboard sensitivity | delivery: independent inspection and intentionally broken private example |

No verification, frequency, area, process, physical power budget, board result,
timing closure or physical sign-off is claimed by this specification.
