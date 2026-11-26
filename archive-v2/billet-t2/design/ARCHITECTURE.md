# BILLET-T2 architecture and frozen internal interfaces

## Ownership and integration

`billet_t2_top` is the only public top, with no parameters. Compile all five
`rtl/*.sv` files as SystemVerilog. No package, generated ROM file, reference RTL,
runtime metadata or private state is needed by the delivered datapath.
The top literally instantiates `billet_t2_bitrev`, `billet_t2_twiddle_rom`,
`billet_t2_butterfly` and `billet_t2_bfp_scaler`.

The following internal contracts are frozen before RTL implementation. All
modules have no parameters. Unqualified control ports are one bit. Arithmetic
ports explicitly marked signed must be connected without changing their widths.

| Module | Inputs | Outputs | Meaning |
| --- | --- | --- | --- |
| `billet_t2_bitrev` | `idx[7:0]`, `log2_n[3:0]` | `rev_idx[7:0]` | Combinational reversal of exactly the low `log2_n` bits; upper output bits zero. Legal widths 4..8 supplied by top. |
| `billet_t2_twiddle_rom` | `k[6:0]`, `ifft` | signed `w_re[16:0]`, `w_im[16:0]` | Combinational canonical 256-grid forward ROM, addresses 0..127. IFFT negates the sign-extended imaginary constant, including -32768 -> +32768. |
| `billet_t2_butterfly` | signed `a_re/a_im/b_re/b_im[15:0]`, signed `w_re/w_im[16:0]` | signed `y0_re/y0_im/y1_re/y1_im[17:0]` | Combinational, unscaled and unclipped complex radix-2 butterfly. |
| `billet_t2_bfp_scaler` | `clk`, `rst_n`, `frame_start`, `stage_start`, `observe_valid`, `stage_commit`, `scale_mode[1:0]`, `stage_shift_bit`, signed `raw0_re/raw0_im/raw1_re/raw1_im[17:0]`, signed `norm_re/norm_im[17:0]` | signed `scaled_re/scaled_im[15:0]`, `sat_inc[1:0]`, `block_exp[3:0]`, `stage_shift` | Accumulate headroom from all four observed butterfly components. Combinationally scale and clamp the registered normalization operand; `sat_inc` counts its clamped components (0..2). Top consumes it only on normalization writes. |

Scaler control is sampled pre-edge. `frame_start` clears exponent and headroom.
`stage_start` clears only headroom. `observe_valid` ORs any signed-16 range
violation into headroom. Clear has priority over observation; top never observes
on a clear edge. `stage_shift` is 1 for mode 0, `stage_shift_bit` for mode 1, and
accumulated headroom for mode 2. Mode 3 never reaches an active frame.
`stage_commit` increments exponent by the actual `stage_shift`, on the final
normalization write, not the final butterfly. Commit and next-stage start
coincide: exponent consumes the old decision and headroom clears for the next
stage. Frame start has exponent priority over commit; reset overrides all.
The combinational scaled outputs and `sat_inc` are meaningful to the top only
in `NORMALIZE_WRITE`; they are not separately handshaken.

## Storage, arithmetic and dependencies

The top owns one 256 x 32-bit sample bank (`{re,im}`, 8192 bits) and one
256 x 36-bit scratch bank (`{raw_re,raw_im}`, 9216 bits). Total logical bank
capacity is 17408 bits, excluding operand/control registers and twiddle logic.
No reset loop initializes banks. Every consumed address is written by the active
frame before use. Reset invalidates the frame, not bank contents.

Input loading writes one bit-reversed location per transfer. Each butterfly
reads two sample entries on one clock and writes two scratch entries on the next.
After all N/2 butterflies, each scratch entry is read on one clock and normalized
back to the sample bank on the next. No normalization write overlaps an operand
read. Output fetch reads one sample into a holding register, then sends it.
These are logical port requirements, not a promise of SRAM or FPGA RAM inference.

At stage s, `half_span=1<<s`, `j=butterfly_count & (half_span-1)`,
`a=((butterfly_count>>s)<<(s+1))+j`, `b=a+half_span`.
Twiddle address `j<<(7-s)` implements selected-length stride `256/N` without
multiple fixed-length cores. Only stages 0..log2(N)-1 execute.

Four signed 16 x 17 products are retained in signed 33 bits. Sign extension
precedes signed 34-bit complex add/subtract. Arithmetic shift by 15 happens
before the signed 35-bit addition/subtraction of a. Signed 18-bit raw components
are lossless for the reachable input/twiddle range. All raw components survive
until the frame-wide stage headroom decision is complete. The scaler shifts
the signed raw operand zero or one bit, then clamps to signed 16 bits.
Top adds `sat_inc` through a 33-bit sum, clamps the cumulative counter to
0xffffffff and sets a reset-only sticky overflow flag.

| Consumer assumption | Producer guarantee |
| --- | --- |
| Bit reversal sees a legal width | First transfer is blocked for invalid live configuration; later transfers use latched width. |
| Butterfly operands are initialized | Counted loading writes all N distinct bit-reversed entries; later stages read only completed normalization results. |
| Normalizer sees the complete stage decision | Last observation occurs before the first normalization read, with no decision bubble. |
| Next stage sees finalized samples and cleared headroom | Last normalization write commits exponent and clears headroom at the same edge that enters the next read state. |
| Output exponent includes final stage | Final commit precedes output fetch. |
| Output holding register cannot be overwritten under stall | Only FETCH updates it; stalled SEND does not advance. |
| No new frame overwrites live data | Ready remains low until the last output handshake completes. |

## Cycle & Degenerate-Boundary Table

All transfers and actions below use **pre-edge** inputs/state; state and register
updates are visible **post-edge**. Reset is asynchronous active-low.

| Pre-edge condition/state | Edge action and post-edge result |
| --- | --- |
| `rst_n=0` in any phase | Abort frame; zero public outputs, diagnostics, exponent and control registers. No bank writes. |
| First clock after reset release | Idle ready reflects legal live configuration; first valid/ready sample may be accepted on this edge. Invalid configuration leaves idle and asserts `cfg_error`. |
| Idle LOAD, first accepted sample | Latch all config; clear scaler frame state; write sample at bit-reversed address zero; set active and load count to one. |
| Active LOAD, input bubble | No write or progress, regardless of live config or `in_last`. |
| Active LOAD, Nth transfer (`t=0`) | Write final sample; start stage zero; enter BUTTERFLY_READ. |
| BUTTERFLY_READ | Register sample operands; enter BUTTERFLY_WRITE. |
| BUTTERFLY_WRITE | Write two raw outputs and observe all four components; advance butterfly or enter NORMALIZE_READ after N/2 butterflies. |
| NORMALIZE_READ | Register one scratch entry; enter NORMALIZE_WRITE. |
| NORMALIZE_WRITE | Write scaled/clamped sample and accumulate diagnostics; advance entry or commit stage. |
| Last NORMALIZE_WRITE, nonfinal stage | Simultaneously commit old shift, clear headroom, increment stage and enter BUTTERFLY_READ. No read/write collision or extra cycle. |
| Last NORMALIZE_WRITE, final stage | Commit final shift and enter OUTPUT_FETCH. |
| OUTPUT_FETCH | Register sample payload; enter OUTPUT_SEND, asserting valid after edge. |
| OUTPUT_SEND, not ready | Hold state, bin, payload, last and exponent. |
| OUTPUT_SEND, ready, nonfinal bin | Accept output, increment bin, enter OUTPUT_FETCH; invalid payload is zero. |
| OUTPUT_SEND, ready, final bin | Accept last output, enter idle LOAD, clear active and pulse `frame_done` for the following cycle. New input can first transfer at the next edge. |
| N=16 / N=256 | Same hardware; 4 / 8 stages, 8 / 128 butterflies per stage; 4 / 8 bit load reversal. Nine-bit length register represents 256 without wrapping. |
| `cfg_log2_n=0,3,9,15` or mode 3 idle | No input acceptance, `cfg_error=1`. During an active frame live config is ignored and error is zero. |
| Mask bits above active stages | Ignored. Each active bit is consumed at exactly its corresponding stage. |
| Raw -32768 / 32767 | Fits without BFP shift; -32769 / 32768 triggers one stage shift. Negative odd shifts floor. |
| Reset concurrent with write/commit/handshake | Reset wins; no transfer or normalization event counts. Already accumulated diagnostics are also cleared by reset. |

There are no DEPTH/MAX_WORDS or other public parameter tuples. Length one,
non-power-of-two lengths and single-beat transforms are not supported cases.
`in_last` never changes the accepted-sample count.

Each stage takes N butterfly clocks plus 2N normalization clocks. Relative to
the final load edge t=0, first valid asserts after t=3*N*log2(N)+1, first output
can transfer at t=3*N*log2(N)+2, and continuous-ready final acceptance occurs
at t=3*N*log2(N)+2*N. Input bubbles and output stalls affect only their phases.
The first-valid bounds are 193 clocks for N=16 and 6145 for N=256; these are
schedule-derived values, not measured timing frequency or physical throughput.

## Verification boundary

Designer supplies these contracts and RTL, not the functional oracle or harness.
Verifier owns `tests/*`, real Icarus/vvp behavior and unchanged T1 comparison,
direct mathematical checks, numerical demonstrations and generic Yosys synthesis.
Expected retained claim evidence destinations are
`../evidence/verification/behavior/` and `../evidence/verification/synthesis/`;
their existence and success must be established independently. No claim here
depends on runtime metadata or a final product report.
