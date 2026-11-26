# BILLET-T3 architecture

## Datapath and ownership

```
four raw rings -> channel_buf -> window -> fft_core -> power_spectrum
                                              |          |
                                              +--- complex/power stream
```

`billet_t3_top` contains literal instances `channel_buf`, `window`, `fft_core`
and `power_spectrum`. `fft_core` contains literal instances `bitrev`,
`twiddle_rom`, `butterfly` and `bfp_scaler`. All modules are delivered as
`rtl/billet_t3_*.sv`. No reference RTL is required to elaborate the top.

`channel_buf` owns per-channel configuration, epoch-valid, fill count, write
pointer, pending reservation and chronological base pointer. A single selected
channel/index pair owns the frame-transfer interface until its last handshake.
Each ring has 256 complex 32-bit words (1024 bytes); total raw storage is 4096
bytes. Wrap uses the effective N, not the physical capacity. Completion of N
stored samples records the next write pointer as the oldest sample's address.
The frame-read address is (base + chronological index) modulo N.

While pending, no producer write can touch that channel's ring. On final
transfer the full reservation is released. The write pointer is already at
the oldest position, ready to replace exactly the oldest N/2 entries in overlap
mode. Retaining fill=N/2 and the pointer preserves the newest half without
copying. Non-overlap resets fill to zero and starts a new configuration epoch
at its next accepted input. The completed non-overlap ring has wrapped its
write pointer to zero, so changing N between frames is safe.

The arbiter searches four pending bits from registered round-robin priority.
Selection is registered and ignores same-edge newly created reservations.
After a selected frame finishes, priority becomes selected+1 modulo four.
A selected waiting frame can hold f_valid while the core computes a prior
frame; its ring remains protected. Other channels remain writable until their
own reservations fill. There is no global input FIFO or global arrival order.

The combinational window uses the chronological index; the core bit reverses
only afterward. The coefficient ROM shares both real and imaginary paths.
Mirroring first-half constants enforces exact finite-length symmetry. RTL
contains no real arithmetic, runtime coefficient generation or external data
file. Rectangular mode bypasses the two signed multipliers completely.

The transform retains the Gen-2 serial state sequence and storage:
256 x 32-bit normalized complex words (1024 bytes), 256 x 36-bit raw
butterfly words (1152 bytes), operand registers and one shared butterfly.
Together with rings, primary sample storage is 6272 bytes, before control and
coefficient logic. These are logical capacities, not measured implementation
area. Two raw writes occur per butterfly; normalization and input loading are
mutually exclusive phases. No sample memory is reset: validity and complete
initialization before reading prevent use of old memory content.

Stage-wide headroom observation precedes normalization. The scaler receives
all raw butterflies, chooses one shift for the stage and accumulates exponent
only at stage commit. The core accumulates component saturations globally.
The top supplies captured frame configuration, never live input configuration,
to this core. Its channel tag captures on the first frame handshake, remains
unchanged through output stalls, and is separately retained for completion.
Power squares the delivered saturated 16-bit components with 32-bit signed
products, then adds their nonnegative unsigned representations at 32 bits.
The mathematical maximum is 2^31, so the result is exact.

## Module contracts and dependencies

| Producer / owner | Consumer | Guarantee |
|---|---|---|
| input source | channel_buf | Only pre-edge in_valid && in_ready consumes data; pins need describe only offered channel |
| channel_buf | window / fft_core | Legal captured config, 0<=f_idx<N, chronological contiguous frame, stable stalled payload |
| window | fft_core input storage | Combinational signed-16 result, no latency or additional handshake |
| fft_core | channel_buf | f_ready only in LOAD; no acceptance on final-output edge |
| fft_core | output sink / power | Natural-order valid bins; stable stalled payload; global saturation status |
| top tag state | output sink | One channel throughout frame; completed tag only during done pulse |
| output sink | scheduling liveness | Eventual readiness required for progress; indefinite stall is legal |

The channel-buffer public internal interface includes clk/rst_n/in_valid/
in_last/in_re/in_im/ch_id, all top configuration inputs, in_ready/cfg_error and
f_ready/f_valid/f_last/f_re/f_im/f_idx/f_ch_id/f_log2_n/f_ifft/f_scale_mode/
f_stage_shift_mask/f_overlap_mode/f_window_mode. Widths and signedness match
their corresponding top ports; f_idx is unsigned 8-bit chronological position.
All f payload and metadata are zero unless f_valid; all exposed outputs are
zero during reset.

The window's combinational interface is signed-16 in_re/in_im and out_re/out_im,
unsigned-8 sample_idx, unsigned-4 log2_n and unsigned-2 window_mode. It receives
only legal accepted frame inputs. The power unit has signed-16 in_re/in_im and
unsigned-32 out_power. `fft_core` preserves every Gen-2 top port name, width and
signedness, without adding channel/window/overlap ports.

## Scheduling, integration and limits

The exact pre-edge/post-edge and boundary table in [SPEC.md](SPEC.md) is
normative. Each stage costs N butterfly cycles plus 2*N normalization cycles.
The first output follows the final frame-load edge by 3*N*log2(N)+1 cycles.
Each subsequent nonstalled bin takes two cycles; all timing is in clock cycles,
not an inferred clock frequency. Registered channel selection may insert
additional gaps between frames.

For integration, compile `rtl/*.sv` with top `billet_t3_top`, assert rst_n low
to clear control asynchronously, then release reset with stable clocking.
Offer a legal configuration and channel with valid sample data; keep offered
beats until their handshake. Drive out_ready according to sink capacity and
consume only valid/ready bins. Configuration has no default epoch: every
channel's first accepted sample captures its explicit settings. Use reset to
change an overlap stream's settings. Reset cancels outstanding work rather
than completing it.

This conservative architecture trades input backpressure for simple ownership:
at most four reserved raw frames, one transform frame, and no independent
output FIFO. One shared transform avoids replicated arithmetic but limits
aggregate throughput. Four channels do not imply four simultaneous FFTs.
Output stalls eventually fill every eligible ring and backpressure input.
No CDC, host bus, DMA, filter, overlap reconstruction, physical target or
deployment flow is included.

Independent verification prerequisites, executable commands, output/source
separation and claim-to-check mapping are in SPEC.md. The Designer supplies
RTL/docs only; Verifier supplies tests and functional/synthesis evidence.
The shared runtime creates any final product report only after independent
engineering acceptance.
