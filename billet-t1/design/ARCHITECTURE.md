# BILLET-T1 architecture

## Hierarchy and dependencies

`billet_t1_pkg` defines shared numerical constants. `billet_t1_top` literally
instantiates `billet_t1_buffer_sched`, `billet_t1_bitrev`,
`billet_t1_twiddle_rom` and `billet_t1_butterfly`. Control is separated from
sample arithmetic to avoid a combinational scheduling feedback path.

| Block | Responsibility and dependency |
| --- | --- |
| Package | 16-bit samples, 32-bit products, 33-bit complex intermediates, 34-bit butterfly sums, 15 fractional bits |
| Bit reversal | Reverse exactly LOG2_N bits of the natural load index |
| ROM | Literal Q1.15 256-point table; legal smaller N uses stride 256/N |
| Butterfly | Four signed multiplications, widened complex sums, two floor shifts, four independent clamps |
| Scheduler | Fixed-count framing, complete stage/address enumeration, bank ownership, output handshake |
| Top | Two sample banks, synchronous operand/output capture, telemetry, public reset/invalid-output gating |

The butterfly interface is signed `[15:0] a_re,a_im,b_re,b_im,w_re,w_im`,
signed `[15:0] y0_re,y0_im,y1_re,y1_im`, and `[2:0] sat_inc`.
The bit-reversal interface is `[A-1:0] idx,rev_idx`; the ROM interface is
`[A-1:0] k` and signed `[15:0] w_re,w_im`. Both have parameter N_POINTS.
Numerical equations and exact externally observable timing are normative in
`SPEC.md`.

## Storage, ownership and schedule

Two banks each hold N packed 32-bit complex samples `{re,im}`. Capacity is
`2*N*32` bits (16,384 bits at N=256), excluding operand/output holding
registers. Each bank needs two synchronous read/write ports; this is a logical
port contract, not an instantiated technology SRAM. No reset is applied to the
banks, and no read-during-write mode is assumed.

LOAD writes bank 0 at `bitreverse(n)` for each accepted natural-order beat n.
This initializes every location exactly once. Decimation-in-time stage s uses
`half=2^s`, `span=2^(s+1)`, group bases `0,span,...,N-span`, and
`j=0..half-1`:

```
a = base+j
b = a+half
k = j*N/span
```

A linear butterfly counter q=0..N/2-1 yields
`j=q & (half-1)`, `base=(q >> s) << (s+1)`. All address arithmetic is
wider than the final address ports. The READ edge synchronously captures a,b
from the current source bank; the following WRITE edge commits the
combinational butterfly's two results at a,b in the other bank. q, s and
addresses remain constant across that READ/WRITE pair. At the stage's last
WRITE, q returns to zero and source/destination swap atomically. Each stage
covers all addresses once, with distinct a,b; no bank is read and written on
the same edge. Initial source is bank 0, so final bank is LOG2_N modulo 2.

Each stage takes N edges, totaling C=N*LOG2_N. Processing is deliberately
folded to one combinational butterfly, not one sample per clock. Four real
16x16 multipliers implement its complex multiplication; no physical area or
frequency result is implied. There are N*LOG2_N complex sample reads and
writes per frame during computation, plus N load writes and N output reads.

Output uses a dedicated FETCH edge to read one final-bank word into the port-A
operand register, reused as the output holding register, followed by SEND until
acceptance. Port A multiplexes compute/output read addresses and bank-0
load/compute write addresses; port B serves the second compute operand/result.
Thus each bank has only two logical read and two logical write ports, with
mutually exclusive read/write phases. On a stall, there is no fetch or
counter change. Nonfinal acceptance advances the index and selects FETCH;
final acceptance selects LOAD and pulses completion. The holding register is
masked to zero outside SEND. Back-to-back offered frames are losslessly
serialized, not overlapped. The no-stall completion edge is F+C+2*N as defined
in `SPEC.md`.

## Scheduler port contract

The scheduler has parameter N_POINTS; inputs `clk,rst_n,in_valid,out_ready`;
one-bit outputs `in_ready,out_valid,out_last,frame_done,load_we,stage_read,
stage_write,output_fetch,src_bank,dst_bank`; address-width outputs
`load_addr,addr_a,addr_b,twiddle_addr,output_addr,out_bin_idx`; and stage-width
output `stage_idx`. A=max(1,LOG2_N), S=max(1,$clog2(LOG2_N)).

`load_addr` is the natural input counter, not yet bit-reversed.
`load_we=in_valid&&in_ready` enables the impending rising-edge bank-0 write.
`stage_read` enables the impending synchronous two-operand read;
`stage_write` enables the impending two-result commit and telemetry increment.
`output_fetch` enables the impending synchronous final-bank output read.
`src_bank` and `dst_bank` identify current compute ownership; during output,
source remains the final bank. `output_addr` identifies the bin to fetch.
`out_bin_idx` is meaningful only with `out_valid` and is otherwise zero.
All controls and address outputs are gated to zero while reset is asserted.
`frame_done` is a registered one-cycle pulse following final SEND acceptance.
No `in_last` input is needed by this fixed-count scheduler.

## Boundaries, reset and numerical reliability

For N=2, A=1, S=1 and stage s=0 has half=1, j=k=0. No zero-width counter
or negative shift is needed. Invalid configurations use guarded dimensions and
an inert generate branch with an explicit simulation diagnostic. Consistent
LOG2_N is also checked at the top. This follows advisory lesson
`exp-6d5cc92e6f5a86894eaae275`: rejection must be executable, not prevented
by invalid dimensions.

Reset clears scheduler state/counters, operand and output registers and
telemetry. It suppresses all memory enables and masks every public output.
Clearing memory is unnecessary because no new frame reads an address before
the complete LOAD initializes bank 0 and subsequent stages initialize their
destination. Aborted frames cannot expose stale output because FETCH is
reachable only after a fresh complete computation.

Four 32-bit products are sign-extended before 33-bit complex arithmetic;
shifted products stay wide, and sign-extended A and T feed 34-bit sums.
Only the final scaled result is clamped to 16 bits. A 33-bit unsigned telemetry
sum detects carry before saturating the sticky 32-bit count. The sticky flag
means any historical component clamp, not a wraparound or malformed marker.
Full-scale square-domain clipping is permitted only according to the exact
equations in `SPEC.md`; it is never hidden or counted repeatedly on stalls.

## Independent acceptance and limitations

Designer supplies RTL and these design documents only. Independent Verifier
owns the integer oracle, separate floating DFT, protocol/reset checks,
coefficient reconstruction, complete address-coverage observations, functional
mutations and real Yosys synthesis. Required sizes include 2,16,64,256.
All numerical outputs must agree bit-exactly with the specified arithmetic;
adequately excited rail-safe quality frames additionally require cosine
similarity >=0.999 and SQNR >=30 dB individually. Deliberate clipping and
low-level/zero cases still require exact integer behavior and truthful metrics.
No functional or synthesis harness is embedded in the design.

Use the package-first command in `SPEC.md` for static elaboration. Synthesis
must read the same complete source hierarchy, select billet_t1_top with the
chosen N_POINTS, lower processes and assert consistency and zero latch cells.
No SRAM macro, external coefficient file, scientific-Python dependency,
private runtime metadata, final product report or past acceptance is a
hardware execution dependency.
