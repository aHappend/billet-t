# Independent BILLET-T2 verification

Run from the project root using installed Python 3 (standard library only),
Icarus `iverilog`/`vvp`, and Yosys. No installation or network access is required.

```sh
python3 tests/verify.py --check behavior --output-dir evidence/verification/behavior
python3 tests/verify.py --check synthesis --output-dir evidence/verification/synthesis
```

An absent output directory is created for the run. If it already exists, a fresh
`run-<uuid>/` child holds the entire new run; failures and prior evidence are
never overwritten or moved. The final JSON stdout line identifies the effective
`result.json` path, whose receipts link all artifacts for that invocation.
An existing non-directory output path remains an error. The shared runtime
executes these admitted checks after handoff.
`tests/prepare.py` creates a unique advisory smoke receipt and tests only N=16
integration plus arithmetic units and negative fixtures; it is **not** a passing
full behavior or synthesis check.

## Requirement-to-check mapping

| Requirement | Independent executable comparison |
| --- | --- |
| All lengths, directions, modes | `make_matrix`: nine directed patterns and three fixed random seeds (17, 89, 503) per length/direction/mode, in one compiled core |
| Programmable scaling | Zero, all ones, all active, alternating, each single active stage, inactive-only masks; per-output exponent and integer samples |
| Numerical arithmetic | Recursive even/odd integer oracle, independently quantized mathematical twiddles, full-width integer products and floor division; no production-source parsing |
| ROM continuity and conjugation | Simulated T1 and T2 ROMs against all 128 generated entries, plus exact inverse conjugates, including +32768 |
| Local arithmetic boundaries | 800 seeded butterflies; every bit-reversal index at all lengths; scaler signed limits, adjacent values, negative odd floors, both normalized components, all four observation lanes, residual clipping, commit/clear priority |
| Stage-wide BFP | Completed-stage decisions; last-butterfly-only trigger; shifted/unshifted stages; full-scale complex corner tone requires residual saturation |
| Framing/configuration | 21 invalid idle configurations; ignored live configuration changes through loading/computation/output stalls; early and absent advisory last markers; exact N accepted inputs |
| Protocol/timing | Every cycle's post-edge and falling-edge public outputs; pre-edge transfers and active X/Z; exact schedule and every normalization-write diagnostic increment; no acceptance while busy, including final output edge |
| Reset | Initial reset low without a preceding toggle, time-zero settled observation and Active-region first rising edge at time 5; asynchronous assertions in loading, both butterfly phases, both normalization phases, fetch and stalled send; fresh frame after every abort |
| Backpressure | Input bubbles and 37-cycle first/last output stalls, intermediate stalls, payload stability, no lost/duplicate outputs, single-cycle done |
| Direct T1 compatibility | Compile unmodified mounted T1; 12 N=256 forward/fixed frames; every component, bin, last, overflow and cumulative counter on every valid output; latency intentionally differs |
| FFT/IFFT reconstruction | Actual unscaled forward RTL outputs become inverse fixed-mode RTL inputs, three low-amplitude seeds per N; no saturation, max component error <=32 LSB, complex-sample RMS <=8 LSB |
| Mathematical orientation | Separate O(N^2) DFT/IDFT; nonsaturating amplitude-64 directional tone peak must be bin 3 / N-3; conservative absolute spectral error bound 4*N LSB; direct DFT check also applied to each reconstruction forward frame |
| BFP dynamic range | Actual amplitude-64 positive real impulse at sample index 1, exponent-rescaled against direct FFT: BFP exponent 0, fixed exponent log2(N), strictly lower BFP squared error at every N; sample-zero impulses remain in the behavior matrix; seeded comparisons reported, not required to universally improve |
| Checker sensitivity | Four bounded private incorrect expected traces (sample, first-valid timing, bit-reversed index, stuck-ready expectation) must exit nonzero with `MISMATCH`; no delivered RTL is mutated |
| Generic synthesis | Native supported `read_verilog -sv` subset; hierarchy checking, process and generic memory lowering, optimization, consistency checks, no latch cells, no unresolved/black-box modules; retained four multipliers, substantive addition/subtraction, >=100 register bits and >=17408 memory bits |

`bridge.sv` never accesses DUT internals. Expected vectors are generated from
the public schedule and mathematical frame results. All payload fields and
diagnostics are compared using case inequality; unknowns cannot pass as zeros.
T1's different intermediate diagnostic timing is not compared with T2's
normalization schedule, but its diagnostics are checked on **every valid output**
and directly compared between the two actual RTL runs. Neither source is modified.

## Evidence and limits

Each subprocess has exact argv/cwd, source hashes, tool versions, UTC times,
timeout status, exit code and raw stdout/stderr in a separate receipt. Generated
vectors, unit bench, simulation binaries, accepted-transfer traces, frame ledger,
functional counters, numerical measurements and Yosys JSON netlist/statistics are
retained. A zero simulator exit is insufficient: completion sentinels, exact
vector counts, nonempty coverage, output conservation and Python assertions must
also pass. Each simulation is a finite generated schedule with a logical cycle
bound including all injected stalls, and each child has a 3600-second wall limit.

`frames.json` records configuration, named pattern/seed, all inputs, expected and
actual samples, exponent, stage decisions and saturation increments, outcome and
raw receipt. `numerical-measurements.json` records actual error quantities and
thresholds; `compatibility.json` binds both actual frame ledgers.
`result.json` is the source-bound overall outcome, never a substitute for raw
evidence. Missing tools, compile failures, malformed vectors, X/Z, mismatches,
timeouts, failed coverage assertions or absent completion propagate nonzero.

No formal proof, physical implementation, PPA, clock frequency, memory-macro
inference or universal BFP improvement is claimed. Finite simulation does not
reach the cumulative 32-bit counter's saturation ceiling (over 2^32 clamp
events); ordinary cumulative increments and reset-only stickiness are compared
throughout. Generic Yosys memory cells retain logical storage, not mapped SRAMs.
Preparation results and failures are advisory and distinct from the full
runtime-owned engineering checks and subsequent independent acceptance.

The original behavior check completed its RTL numerical simulations but first
failed the orientation error assertion at N=64: an unscaled amplitude-900 tone
saturated, giving maximum error 24829.586 LSB versus the unchanged 256 LSB bound.
Read-only analysis of the retained outputs is recorded in
[`orientation-diagnosis-51057280fbcd/retained-orientation-analysis.receipt.json`](../evidence/preparation/orientation-diagnosis-51057280fbcd/retained-orientation-analysis.receipt.json).
Numerical orientation now uses amplitude 64 and explicitly requires zero
saturation; amplitude-900 tones remain in the exact-integer behavior matrix.

The same retained outputs also exposed a subsequent stimulus issue: the
sample-zero amplitude-64 impulse has zero spectral error in **both** modes for
N=16,32,64. That read-only analysis is recorded in
[`numerical-diagnosis-dd94698860c9/retained-numerical-analysis.receipt.json`](../evidence/preparation/numerical-diagnosis-dd94698860c9/retained-numerical-analysis.receipt.json).
The numerical demonstration now uses a sample-index-1 positive impulse of the
same amplitude, exercising twiddle quantization without changing any threshold,
arithmetic, exponent or saturation requirement. The specification does not
restrict impulse position. Original failure evidence and the sample-zero
behavior-matrix cases are retained unchanged.
The first focused repair probe, which changed only impulse position, preserved
the orientation failure in
[`numerical-repair-9ed6a941a17c/receipt.json`](../evidence/preparation/numerical-repair-9ed6a941a17c/receipt.json).
The corrected focused Icarus/vvp numerical probe is retained in
[`numerical-repair-fe97bf3cf240/receipt.json`](../evidence/preparation/numerical-repair-fe97bf3cf240/receipt.json):
all 15 reconstructions passed (worst component error 5 LSB, worst complex RMS
2.003903 LSB), all ten nonsaturating orientation checks passed, and all five
delayed-impulse BFP comparisons strictly improved with the required exponents.
This is advisory numerical preparation, not full behavior, compatibility,
synthesis or engineering acceptance; the shared runtime must execute the
unchanged admitted checks against the repaired verification sources.

The next runtime retry failed before executing any check: creating the existing
`evidence/verification/behavior/` directory raised `FileExistsError`. This was an
output-namespace harness defect, not a new numerical result. Fresh child
directories now permit the unchanged admitted command to retry while preserving
the original failed result and every raw artifact. A bounded synthetic entrypoint
probe exercises failed-then-successful retries, fresh-process dispatch for both
check choices, result-path reporting and rejection of a regular-file output
path; it does not simulate RTL or certify behavior or synthesis.
