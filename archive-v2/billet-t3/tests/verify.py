#!/usr/bin/env python3
"""BILLET-T3 independent checks, with immutable raw tool/source receipts.

Requirement -> executable observation:
* all N/directions/scaling/windows: numerical-matrix exact integer comparison;
  mathematical low-amplitude DFT plausibility and direct native Gen-2 runs;
* channels/epochs/overlap/wrap/fairness: accepted-sample queues, independent
  channel-buffer public interface, four pending contexts and repeated wraps;
* reset/invalid/stalls/latency/done: every pre/post edge, time-zero, first Active
  posedge and negedge reset checks; inactive zeros and active X/Z rejection;
* reachability/synthesizability: real Yosys generic synthesis, hierarchy,
  port widths/signedness, substantive logic and no inferred latches;
* delivery/sensitivity: source-only reproduction and a private stuck-zero-power
  RTL defect rejected by the unchanged public transaction scoreboard.

Coverage is bounded, not exhaustive or formal. Counter rollover at 2**32
component saturations is not claimed exercised by simulation. No physical
implementation, timing, area, power or board claims are made.
"""
import argparse
from collections import Counter, deque
import json
from pathlib import Path
import random
import re
import sys
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parent))
import bridge
import model
from retention import ROOT, Run, hashes, stamp, write
import scenarios


def require(condition, message):
    if not condition:
        raise AssertionError(message)


def legal(cfg):
    return 4 <= cfg[0] <= 8 and cfg[2] != 3 and cfg[5] != 3


class Assembler:
    """Queues are mathematical chronological histories, never DUT ring pointers."""
    def __init__(self):
        self.cfg = [None] * 4
        self.history = [[] for _ in range(4)]
        self.frames = [deque() for _ in range(4)]
        self.accepted = [0] * 4
        self.created = [0] * 4

    def accept(self, ch, pair, pins, cycle):
        cfg = self.cfg[ch]
        if cfg is None:
            require(legal(pins), "Accepted illegal configuration")
            cfg = self.cfg[ch] = pins
        history = self.history[ch]
        history.append(pair)
        self.accepted[ch] += 1
        n = 1 << cfg[0]
        require(len(history) <= n, "Sample history exceeded mathematical frame")
        if len(history) != n:
            return None
        self.created[ch] += 1
        frame = {"samples": history[:], "cfg": cfg, "cycle": cycle, "ch": ch,
                 "accepted_samples": self.accepted[ch], "sequence": self.created[ch],
                 "result": model.transform(history, cfg)}
        self.frames[ch].append(frame)
        self.history[ch] = history[n // 2:] if cfg[4] else []
        if not cfg[4]:
            self.cfg[ch] = None
        return frame


class Scoreboard:
    def __init__(self, scenario):
        self.scenario = scenario
        self.counts = Counter()
        self.configs = set()
        self.witnesses = {}
        self.ledger = []
        self.reset()

    def reset(self):
        self.a = Assembler()
        self.current = None
        self.index = 0
        self.saturations = self.status = 0
        self.done = (0, 0)
        self.next_valid = None
        self.priority = 0
        self.buffer_active = None
        self.last_cycle = None

    def event(self, name, cycle, **detail):
        self.counts[name] += 1
        if name not in self.witnesses:
            self.witnesses[name] = {"cycle": cycle, **detail}

    def config_check(self, pre, ch, cfg, exact_ready=False):
        expected_error = self.a.cfg[ch] is None and not legal(cfg)
        require(pre["cfg_error"] == expected_error, "cfg_error capture/epoch mismatch")
        if expected_error:
            require(pre["in_ready"] == 0, "Illegal configuration ready")
        if exact_ready:
            expected_ready = not self.a.frames[ch] and not expected_error
            require(pre["in_ready"] == expected_ready, "Channel reservation readiness")

    def status_check(self, value):
        sat = value["saturation_count"]
        require(sat >= self.status, "Saturation counter decreased without reset")
        require(value["overflow_flag"] == (sat > 0), "Sticky overflow/count mismatch")
        self.status = sat

    def top_payload(self, value, cycle, phase):
        if not value["out_valid"]:
            for name in ("out_re", "out_im", "out_power", "out_bin_idx",
                         "out_block_exp", "out_ch_id", "out_last"):
                require(value[name] == 0, f"Inactive payload {name} != 0")
            return
        ch = value["out_ch_id"]
        if self.current is None:
            require(self.a.frames[ch], f"Unsolicited output channel {ch}")
            self.current = self.a.frames[ch][0]
            self.index = 0
            result = self.current["result"]
            self.saturations = min(0xffffffff, self.saturations + result["saturations"])
            self.configs.add(self.current["cfg"])
            if self.scenario.isolated:
                n = len(result["bins"])
                delay = 3 * n * self.current["cfg"][0] + 1
                if self.scenario.kind == "top":
                    delay += n + 1
                require(phase == "post", "First valid not observed at a post-edge")
                require(cycle == self.current["cycle"] + delay,
                        f"First-output latency cycle={cycle}, final input="
                        f"{self.current['cycle']}, required delay={delay}")
                self.event("exact_first_output_latency", cycle, delay_cycles=delay)
        f = self.current
        require(ch == f["ch"], "Interleaved or corrupt channel tag")
        require(value["out_bin_idx"] == self.index, "Bin order/index mismatch")
        expected = f["result"]["bins"][self.index]
        actual = value["out_re"], value["out_im"]
        require(actual == expected,
                f"Complex mismatch ch={ch} bin={self.index} cfg={f['cfg']}: "
                f"actual={actual} expected={expected}")
        if self.scenario.kind == "top":
            power = sum(x*x for x in expected)
            require(value["out_power"] == power,
                    f"Power mismatch ch={ch} bin={self.index}: "
                    f"{value['out_power']} != {power}")
        require(value["out_block_exp"] == f["result"]["exponent"], "Block exponent")
        require(value["out_last"] == (self.index == len(f["samples"]) - 1),
                "Last beat mismatch")
        require(value["saturation_count"] == self.saturations,
                f"Global saturation count: {value['saturation_count']} != {self.saturations}")
        self.counts["valid_payload_comparisons"] += 1

    def top(self, cycle, rst, inp, pre, post):
        valid, last, r, im, ch, *rest = inp
        cfg, ready = tuple(rest[:6]), rest[6]
        if not rst:
            require(not any(pre.values()) and not any(post.values()), "Reset public zeros")
            self.event("reset_cycles", cycle)
            if self.current or any(self.a.frames):
                self.event("reset_with_outstanding", cycle)
            if self.current is not None:
                self.counts["reset_aborted_output_beats"] += self.index
            if any(self.a.history):
                self.event("reset_with_history", cycle)
            self.reset()
            return
        if self.scenario.kind == "top":
            self.config_check(pre, ch, cfg)
        if pre["cfg_error"]:
            self.event("invalid_valid" if valid else "invalid_idle", cycle, cfg=cfg, ch=ch)
        if valid and not pre["in_ready"] and not pre["cfg_error"]:
            self.event("input_backpressure_cycles", cycle, ch=ch)
        if self.a.cfg[ch] is not None and not legal(cfg) and pre["in_ready"]:
            self.event("captured_invalid_pins_ignored", cycle, ch=ch)
        self.status_check(pre)
        self.top_payload(pre, cycle, "pre")
        require((pre["frame_done"], pre["frame_done_ch_id"]) == self.done,
                "Completion pulse/tag duration")
        accepted_output = pre["out_valid"] and ready
        completed = accepted_output and pre["out_last"]
        done_ch = pre["out_ch_id"] if completed else 0
        if pre["out_valid"] and not ready:
            where = ("last" if pre["out_last"] else
                     "first" if pre["out_bin_idx"] == 0 else "middle")
            self.event("output_stall_" + where, cycle, ch=pre["out_ch_id"],
                       bin=pre["out_bin_idx"])
            require(all(post[k] == pre[k] for k in (
                "out_valid", "out_last", "out_re", "out_im", "out_power",
                "out_bin_idx", "out_block_exp", "out_ch_id")), "Stall instability")
        if accepted_output:
            self.event("output_beats", cycle)
            require(not post["out_valid"], "Output did not enter fetch/load after accept")
            if completed:
                f = self.a.frames[done_ch].popleft()
                self.ledger.append({
                    "cfg": f["cfg"], "channel": done_ch,
                    "last_input_cycle": f["cycle"], "completion_cycle": cycle,
                    "accepted_samples": f["accepted_samples"], "sequence": f["sequence"],
                    "compared_bins": self.index + 1,
                    "required_bins": len(f["samples"]), "outcome": "passed",
                    "saturations": f["result"]["saturations"],
                    "block_exponent": f["result"]["exponent"]})
                self.event("frames", cycle, ch=done_ch, cfg=f["cfg"])
                if f["cfg"][4] and f["accepted_samples"] >= 3 * len(f["samples"]):
                    self.event("overlap_repeated_wrap_compared", cycle, ch=done_ch,
                               accepted_samples=f["accepted_samples"])
                if f["result"]["saturations"]:
                    self.event("saturating_frames", cycle)
                if f["cfg"][2] == 2 and f["result"]["exponent"] == 0:
                    self.event("bfp_no_shift_frame", cycle)
                if f["cfg"][2] == 2 and f["result"]["exponent"] > 0:
                    self.event("bfp_shift_frame", cycle)
                self.current = None
                self.index = 0
            else:
                self.index += 1
                self.next_valid = cycle + 1
        if valid and pre["in_ready"]:
            self.event("input_beats", cycle)
            if accepted_output:
                self.event("simultaneous_input_output", cycle)
            frame = self.a.accept(ch, (r, im), cfg, cycle)
            if frame is not None:
                self.event("assembled_frames", cycle, ch=ch)
        if not pre["out_valid"] and not post["out_valid"] and not any(self.a.frames):
            for c, history in enumerate(self.a.history):
                captured = self.a.cfg[c]
                if captured and len(history) == (1 << captured[0]) - 1:
                    name = ("hop_minus_one_quiet" if captured[4] and self.a.created[c]
                            else "n_minus_one_quiet")
                    self.event(name, cycle, ch=c, accepted_samples=self.a.accepted[c])
        if self.next_valid == cycle:
            require(post["out_valid"], "Next-bin fetch latency not one post-edge")
            self.next_valid = None
            self.event("exact_interbin_latency", cycle)
        self.status_check(post)
        self.top_payload(post, cycle, "post")
        self.done = (int(completed), done_ch)
        require((post["frame_done"], post["frame_done_ch_id"]) == self.done,
                "Completion not exactly after final handshake")
        if completed:
            self.event("done_after_last_handshake", cycle, ch=done_ch)
        if not post["frame_done"]:
            require(post["frame_done_ch_id"] == 0, "Inactive done tag")

    def buffer_payload(self, value):
        if not value["f_valid"]:
            require(all(value[n] == 0 for n, _ in bridge.BUFFER_FIELDS
                        if n not in ("in_ready", "cfg_error")), "Inactive buffer payload")
            return
        ch = value["f_ch_id"]
        require(self.a.frames[ch], "Buffer emitted frame before N accepted samples")
        f = self.a.frames[ch][0]
        cfg = f["cfg"]
        require(ch == self.buffer_active, "Frame stream not contiguous")
        require(value["f_idx"] == self.index, "Chronological frame index")
        require((value["f_re"], value["f_im"]) == f["samples"][self.index],
                f"Raw chronology mismatch ch={ch} idx={self.index}")
        got_cfg = tuple(value[k] for k in (
            "f_log2_n", "f_ifft", "f_scale_mode", "f_stage_shift_mask",
            "f_overlap_mode", "f_window_mode"))
        require(got_cfg == cfg, "Frame configuration metadata")
        require(value["f_last"] == (self.index == len(f["samples"]) - 1),
                "Frame chronological last")
        self.counts["valid_payload_comparisons"] += 1

    def buffer(self, cycle, rst, inp, pre, post):
        valid, last, r, im, ch, *rest = inp
        cfg, ready = tuple(rest[:6]), rest[6]
        if not rst:
            require(not any(pre.values()) and not any(post.values()), "Buffer reset")
            self.event("reset_cycles", cycle)
            self.reset()
            return
        self.config_check(pre, ch, cfg, exact_ready=True)
        if valid and not pre["in_ready"] and not pre["cfg_error"]:
            self.event("input_backpressure_cycles", cycle, ch=ch)
        self.buffer_payload(pre)
        pending_before = [bool(q) for q in self.a.frames]
        if all(pending_before):
            self.event("all_four_reserved", cycle)
        if valid and pre["in_ready"]:
            self.a.accept(ch, (r, im), cfg, cycle)
            self.event("input_beats", cycle)
        if pre["f_valid"] and ready:
            if valid and pre["in_ready"]:
                self.event("simultaneous_input_frame_transfer", cycle)
            self.event("frame_beats", cycle)
            if pre["f_last"]:
                self.a.frames[self.buffer_active].popleft()
                self.priority = (self.buffer_active + 1) % 4
                self.buffer_active = None
                self.index = 0
                self.event("frames", cycle)
                require(not post["f_valid"], "No registered release gap")
            else:
                self.index += 1
                require(post["f_valid"], "Frame transfer became noncontiguous")
        elif pre["f_valid"]:
            require(all(post[k] == pre[k] for k, _ in bridge.BUFFER_FIELDS
                        if k not in ("in_ready", "cfg_error")), "Frame stall stability")
            self.event("frame_stalls", cycle)
            if pre["f_last"]:
                self.event("frame_last_stalls", cycle)
        if not pre["f_valid"]:
            expected = next((c for offset in range(4)
                             if pending_before[c := (self.priority + offset) % 4]), None)
            require(bool(post["f_valid"]) == (expected is not None),
                    "Registered selection timing/early reservation consumption")
            if expected is not None:
                require(post["f_ch_id"] == expected, "Round-robin choice")
                self.buffer_active = expected
                self.index = 0
                self.event("round_robin_selections", cycle, ch=expected)
        self.buffer_payload(post)

    def compare(self, trace):
        expected_cycle = 0
        with trace.open() as source:
            for line in source:
                values = line.split()
                require(len(values) == 17, "Malformed trace")
                asynchronous = values[0] == "A"
                cycle = expected_cycle if asynchronous else int(values[0])
                command, rst = map(int, values[1:3])
                require(cycle == expected_cycle, "Trace cycle omission or duplication")
                if not asynchronous:
                    expected_cycle += 1
                else:
                    self.event("asynchronous_reset_without_clock", cycle)
                inp = list(map(int, values[3:15]))
                fields = (bridge.BUFFER_FIELDS if self.scenario.kind == "buffer"
                          else bridge.TOP_FIELDS)
                pre, post = [bridge.decode(v, fields) for v in values[15:]]
                try:
                    if self.scenario.kind == "buffer":
                        self.buffer(cycle, rst, inp, pre, post)
                    else:
                        self.top(cycle, rst, inp, pre, post)
                except AssertionError as e:
                    raise AssertionError(f"{self.scenario.name}: cycle={cycle} "
                                         f"command={command}: {e}") from e
        require(expected_cycle > 0, "Empty simulation trace")
        require(self.current is None and not any(self.a.frames), "Undrained frames at EOF")
        require(self.counts["frames"] > 0, "No compared completed frames")
        return {"name": self.scenario.name, "kind": self.scenario.kind,
                "seed": self.scenario.seed,
                "cycles": expected_cycle, "observed": dict(self.counts),
                "configurations": sorted(self.configs),
                "witnesses": self.witnesses, "frames": self.ledger,
                "raw_trace": str(trace.relative_to(ROOT)), "outcome": "passed"}


def simulate(run, scenario, kind=None, rtl=None, suffix=""):
    kind = kind or scenario.kind
    stem = scenario.name + suffix
    vectors = run.directory / (stem + ".vectors")
    trace = run.directory / (stem + ".trace")
    generated = run.directory / (stem + ".sv")
    binary = run.directory / (stem + ".vvp")
    vectors.write_text("".join(" ".join(map(str, row)) + "\n" for row in scenario.rows))
    generated.write_text(bridge.bench(kind, str(vectors), str(trace)))
    sources = (sorted((ROOT / "billet_t2_reference/rtl").glob("*.sv"))
               if kind == "reference" else
               (rtl if rtl is not None else sorted((ROOT / "rtl").glob("*.sv"))))
    run.execute(stem + "-compile", ["iverilog", "-g2012", "-Wall", "-s", "tb",
                                    "-o", str(binary), str(generated), *map(str, sources)])
    run.execute(stem + "-simulate", ["vvp", str(binary)])
    return trace


def mathematical_checks():
    rng = random.Random(109)
    rows = []
    for logn in range(4, 9):
        n = 1 << logn
        for inverse in range(2):
            for win in range(3):
                cfg = (logn, inverse, 0, 0, 0, win)
                samples = scenarios.data(n, rng, 5)
                integer = model.transform(samples, cfg)
                mathematical = model.dft(model.window(samples, win), inverse)
                error = max(abs(component - ref)
                            for actual, expected in zip(integer["bins"], mathematical)
                            for component, ref in zip(actual, (expected.real/n, expected.imag/n)))
                require(error <= logn + 2, f"Oracle vs mathematical DFT error {error}")
                require(integer["saturations"] == 0, "Low amplitude DFT unexpectedly saturated")
                rows.append({"n": n, "inverse": inverse, "window": win,
                             "max_component_error_lsb": error,
                             "required_max_error_lsb": logn + 2,
                             "compared_bins": n, "outcome": "passed"})
    require(model.twiddle(0, 0) == (32767, 0), "Unity analytical check")
    require(model.twiddle(64, 1) == (0, 32768), "IFFT unity width analytical check")
    require(sum(x*x for x in (-32768, -32768)) == 0x80000000, "Power analytical maximum")
    return rows


def lit(value, width):
    return f"{width}'h{value & ((1 << width)-1):x}"


def unit_checks(run, probe=False):
    rng = random.Random(31)
    lines, vectors = [], []
    counts = Counter()

    def compare(label, assigns, pairs, vector):
        lines.append(assigns + " #1;")
        expr = " || ".join(f"({name} !== {lit(value, width)})"
                           for name, value, width in pairs)
        lines.append(f'if ({expr}) $fatal(1,"UNIT_{label} vector={len(vectors)}");')
        vectors.append({"unit": label, "input": vector,
                        "expected": {name: value for name, value, _ in pairs}})
        counts[label] += 1

    corners = [-32768, -32767, -16385, -1, 0, 1, 16383, 32766, 32767]
    for logn in range(4, 9):
        n = 1 << logn
        for i in range(n):
            for win in range(3):
                for r in ([-32768, -1, 1, 32767] if not probe else [-32768, 32767]):
                    im = corners[(i + win) % len(corners)]
                    expected = model.window([(r, im)] * n, win)[i]
                    compare("window",
                            f"wr={lit(r,16)};wi={lit(im,16)};idx={i};ln={logn};wm={win};",
                            [("window_re", expected[0], 16), ("window_im", expected[1], 16)],
                            [r, im, i, logn, win])
            reverse = int(f"{i:0{logn}b}"[::-1], 2)
            compare("bitrev", f"idx={i};ln={logn};",
                    [("rev", reverse, 8)], [i, logn])
    for inverse in range(2):
        for k in range(128):
            wr, wi = model.twiddle(k, inverse)
            compare("twiddle", f"tk={k};inv={inverse};",
                    [("twr", wr, 17), ("twi", wi, 17)], [k, inverse])
    power_inputs = [(r, i) for r in corners for i in corners]
    power_inputs += [(rng.randint(-32768, 32767), rng.randint(-32768, 32767))
                     for _ in range(128 if probe else 4096)]
    for r, im in power_inputs:
        compare("power", f"pr={lit(r,16)};pi={lit(im,16)};",
                [("power", r*r + im*im, 32)], [r, im])
    for i in range(128 if probe else 4096):
        a = tuple(rng.choice(corners) if i < 81 else rng.randint(-32768, 32767)
                  for _ in range(2))
        b = tuple(rng.choice(corners) if i < 81 else rng.randint(-32768, 32767)
                  for _ in range(2))
        w = model.twiddle(i % 128, (i // 128) % 2)
        p, q = model.butterfly(a, b, w)
        compare("butterfly",
                f"ar={lit(a[0],16)};ai={lit(a[1],16)};br={lit(b[0],16)};"
                f"bi={lit(b[1],16)};bwr={lit(w[0],17)};bwi={lit(w[1],17)};",
                [(name, value, 18) for name, value in
                 zip(("y0r", "y0i", "y1r", "y1i"), (*p, *q))], [a, b, w])
    clock = "sc=0;#1;sc=1;#1;sc=0;"
    compare("scaler_reset", "sc=0;srst=0;sfs=0;sss=0;sob=0;scommit=0;"
            "smode=0;sbit=0;sr0=0;si0=0;sr1=0;si1=0;snr=0;sni=0;",
            [("sre", 0, 16), ("sim", 0, 16), ("sinc", 0, 2),
             ("sexp", 0, 4), ("sshift", 0, 1)], [])
    for mode in range(3):
        exp = 0
        compare("scaler_frame_start", f"srst=1;smode={mode};sfs=1;" + clock,
                 [("sexp", 0, 4)], [mode])
        lines.append("sfs=0;")
        for stage in range(4):
            bit = stage % 2
            compare("scaler_stage_start", f"sss=1;sbit={bit};" + clock,
                     [("sexp", exp, 4)], [mode, stage])
            lines.append("sss=0;")
            observed_overflow = False
            for observation in range(3):
                 value = (-32769 if stage == 2 and observation == 2 else
                          65535 if stage == 1 and observation == 0 else 0)
                 observed_overflow |= not -32768 <= value <= 32767
                 shift = mode == 0 or (mode == 1 and bit) or (
                     mode == 2 and observed_overflow)
                 compare("scaler_observation",
                         f"sob=1;sr0={lit(value,18)};" + clock,
                         [("sshift", int(bool(shift)), 1), ("sexp", exp, 4)],
                         [mode, stage, observation, value])
            lines.append("sob=0;")
            for nr, ni in [(-131072, 131071), (-65537, 65535), (-32769, 32768),
                            (-32768, 32767), (-1, 1), (0, 0)]:
                 rr, ri = nr >> bool(shift), ni >> bool(shift)
                 inc = int(rr != model.clamp(rr)) + int(ri != model.clamp(ri))
                 compare("scaler_normalization",
                         f"snr={lit(nr,18)};sni={lit(ni,18)};",
                         [("sre", model.clamp(rr), 16), ("sim", model.clamp(ri), 16),
                          ("sinc", inc, 2), ("sexp", exp, 4)],
                         [mode, stage, nr, ni, int(bool(shift))])
            exp += int(bool(shift))
            compare("scaler_commit", "scommit=1;" + clock,
                     [("sexp", exp, 4)], [mode, stage])
            lines.append("scommit=0;")
    header = """`timescale 1ns/1ps
module tb;
reg signed [15:0] wr,wi,pr,pi,ar,ai,br,bi;
reg signed [16:0] bwr,bwi;
reg [7:0] idx;
reg [3:0] ln;
reg [1:0] wm;
reg [6:0] tk;
reg inv;
wire signed [15:0] window_re,window_im;
wire signed [16:0] twr,twi;
wire signed [17:0] y0r,y0i,y1r,y1i;
wire [7:0] rev;
wire [31:0] power;
reg sc,srst,sfs,sss,sob,scommit,sbit;
reg [1:0] smode;
reg signed [17:0] sr0,si0,sr1,si1,snr,sni;
wire signed [15:0] sre,sim;
wire [1:0] sinc;
wire [3:0] sexp;
wire sshift;
billet_t3_window window(.in_re(wr),.in_im(wi),.sample_idx(idx),.log2_n(ln),
 .window_mode(wm),.out_re(window_re),.out_im(window_im));
billet_t3_power_spectrum ps(.in_re(pr),.in_im(pi),.out_power(power));
billet_t3_twiddle_rom tw(.k(tk),.ifft(inv),.w_re(twr),.w_im(twi));
billet_t3_bitrev bv(.idx(idx),.log2_n(ln),.rev_idx(rev));
billet_t3_butterfly bf(.a_re(ar),.a_im(ai),.b_re(br),.b_im(bi),
 .w_re(bwr),.w_im(bwi),.y0_re(y0r),.y0_im(y0i),.y1_re(y1r),.y1_im(y1i));
billet_t3_bfp_scaler scaler(.clk(sc),.rst_n(srst),.frame_start(sfs),
 .stage_start(sss),.observe_valid(sob),.stage_commit(scommit),
 .scale_mode(smode),.stage_shift_bit(sbit),.raw0_re(sr0),.raw0_im(si0),
 .raw1_re(sr1),.raw1_im(si1),.norm_re(snr),.norm_im(sni),
 .scaled_re(sre),.scaled_im(sim),.sat_inc(sinc),.block_exp(sexp),.stage_shift(sshift));
initial begin
"""
    source = run.directory / "units.sv"
    source.write_text(header + "\n".join(lines) +
                      f'\n$display("UNIT_COMPARISONS {len(vectors)}");$finish;end\nendmodule\n')
    write(run.directory / "unit-vectors.json", vectors)
    binary = run.directory / "units.vvp"
    run.execute("units-compile", ["iverilog", "-g2012", "-Wall", "-s", "tb",
                                 "-o", str(binary), str(source),
                                 *map(str, sorted((ROOT / "rtl").glob("*.sv")))])
    stdout = run.execute("units-simulate", ["vvp", str(binary)])
    require(f"UNIT_COMPARISONS {len(vectors)}" in stdout.read_text(),
            "Unit comparison execution marker missing")
    return {"compared_vectors": dict(counts), "outcome": "passed",
            "raw_stdout": str(stdout.relative_to(ROOT))}


def behavior(run, probe=False):
    result = {"scope": "bounded preparation subset" if probe else "admitted behavior",
              "runs": []}
    work = [scenarios.matrix(probe), scenarios.compatibility(probe),
            scenarios.overlap(probe), scenarios.boundaries(), scenarios.buffer()]
    if probe:
        work = [work[0], work[1]]
    thresholds = {"numerical-matrix": (90, 8928), "gen2-continuity": (50, 4960),
                  "overlap-repeated-wrap": (64, 8704),
                  "boundaries-invalid-reset-stalls": (13, 448),
                  "channel-buffer-contract": (44, 2624)}
    if probe:
        thresholds = {"numerical-matrix": (3, 288), "gen2-continuity": (2, 32)}
    result["runs"] = [{"name": s.name, "seed": s.seed, "outcome": "not_run",
                       "required_frames": thresholds[s.name][0],
                       "required_beats": thresholds[s.name][1]} for s in work]
    run.result = result
    write(run.directory / "run-plan.json", result["runs"])
    result["mathematical_dft"] = mathematical_checks()
    result["units"] = unit_checks(run, probe)
    for number, scenario in enumerate(work):
        row = result["runs"][number]
        try:
            trace = simulate(run, scenario)
            row.update(Scoreboard(scenario).compare(trace))
            require(row["observed"]["frames"] == row["required_frames"],
                    f"{scenario.name}: frame comparison denominator")
            completed_beats = (row["observed"]["frame_beats"] if scenario.kind == "buffer"
                               else sum(f["compared_bins"] for f in row["frames"]))
            row["compared_complete_frame_beats"] = completed_beats
            require(completed_beats == row["required_beats"],
                    f"{scenario.name}: beat comparison denominator")
            if scenario.kind != "buffer":
                aborted_beats = row["observed"].get("reset_aborted_output_beats", 0)
                row["compared_reset_aborted_beats"] = aborted_beats
                require(row["observed"]["output_beats"] == completed_beats + aborted_beats,
                        "Accepted output conservation across reset epochs")
                required_aborted = 15 if scenario.name == "boundaries-invalid-reset-stalls" else 0
                require(aborted_beats == required_aborted, "Reset-aborted beat denominator")
            if scenario.kind == "core":
                reference = simulate(run, scenario, kind="reference", suffix="-gen2")
                # The native reference is executed, not treated as a passing baseline.
                require(trace.read_bytes() == reference.read_bytes(),
                        "Native Gen-2/T3-core public trace difference")
                row["gen2_differential_cycles"] = row["cycles"]
                row["reference_trace"] = str(reference.relative_to(ROOT))
        except Exception as e:
            row.update(outcome="failed", error=f"{type(e).__name__}: {e}")
            raise
        finally:
            write(run.directory / f"run-result-{number + 1}.json", row)
    if not probe:
        totals = Counter()
        for row in result["runs"]:
            totals.update(row["observed"])
        for required in (
            "output_stall_first", "output_stall_middle", "output_stall_last",
            "reset_with_outstanding", "reset_with_history", "invalid_valid",
            "invalid_idle", "captured_invalid_pins_ignored", "all_four_reserved",
            "round_robin_selections", "frame_stalls", "exact_first_output_latency",
            "exact_interbin_latency", "done_after_last_handshake",
            "saturating_frames", "bfp_no_shift_frame", "bfp_shift_frame",
            "simultaneous_input_frame_transfer", "asynchronous_reset_without_clock",
            "n_minus_one_quiet", "hop_minus_one_quiet",
            "overlap_repeated_wrap_compared", "input_backpressure_cycles",
            "frame_last_stalls"):
            require(totals[required] > 0, "Required observed event absent: " + required)
        expected = {(l, inv, scale, (0, 0x55, 0)[scale], 0, win)
                    for l in range(4, 9) for inv in range(2)
                    for scale in range(3) for win in range(3)}
        actual = set(map(tuple, result["runs"][0]["configurations"]))
        require(actual == expected, "Numerical matrix missing configuration")
        result["observed_totals"] = dict(totals)
    result["coverage_limits"] = [
        "Bounded directed and seeded cases, not exhaustive or formal coverage.",
        "No simulation of 2**32 component saturations / counter rollover.",
        "No process-specific synthesis, clock frequency, physical PPA or deployment."]
    return result


PORTS = {
    "clk": ("input", 1, False), "rst_n": ("input", 1, False),
    **{n: ("input", 1, False) for n in
       ("in_valid", "in_last", "out_ready", "cfg_ifft", "cfg_overlap_mode")},
    **{n: ("input", 16, True) for n in ("in_re", "in_im")},
    **{n: ("input", 2, False) for n in ("ch_id", "cfg_scale_mode", "cfg_window_mode")},
    "cfg_log2_n": ("input", 4, False), "cfg_stage_shift_mask": ("input", 8, False),
    **{n: ("output", 1, False) for n in
       ("in_ready", "out_valid", "out_last", "frame_done", "overflow_flag", "cfg_error")},
    **{n: ("output", 16, True) for n in ("out_re", "out_im")},
    **{n: ("output", 32, False) for n in ("out_power", "saturation_count")},
    "out_bin_idx": ("output", 8, False), "out_block_exp": ("output", 4, False),
    **{n: ("output", 2, False) for n in ("out_ch_id", "frame_done_ch_id")}}


def synthesis(run, probe=False):
    structural, netlist = run.directory / "structural.json", run.directory / "netlist.json"
    script = run.directory / "synthesis.ys"
    sources = sorted((ROOT / "rtl").glob("*.sv"))
    script.write_text(
        "read_verilog -sv " + " ".join(str(p) for p in sources) + "\n"
        "hierarchy -check -top billet_t3_top\n"
        "proc\ncheck -assert\n"
        "select -assert-none t:$dlatch t:$adlatch\n"
        "memory_collect\nopt\n"
        f"write_json {structural}\nstat\n" +
        ("" if probe else "synth -top billet_t3_top -noabc\n"
        "check -assert\nselect -assert-none t:$dlatch t:$adlatch t:$_DLATCH*\n"
        f"write_json {netlist}\nstat\n"))
    stdout = run.execute("yosys-synthesis", ["yosys", "-s", str(script)])
    data = json.loads(structural.read_text())
    modules = data["modules"]
    expected_children = {
        "billet_t3_top": {"channel_buf": "billet_t3_channel_buf",
                          "window": "billet_t3_window", "fft_core": "billet_t3_fft_core",
                          "power_spectrum": "billet_t3_power_spectrum"},
        "billet_t3_fft_core": {"bitrev": "billet_t3_bitrev",
                             "twiddle_rom": "billet_t3_twiddle_rom",
                             "butterfly": "billet_t3_butterfly",
                             "bfp_scaler": "billet_t3_bfp_scaler"}}
    for parent, children in expected_children.items():
        for instance, kind in children.items():
            require(modules[parent]["cells"][instance]["type"] == kind,
                    f"Reachable hierarchy {parent}.{instance}")
            require(bool(modules[kind]["cells"]), "Decorative or empty module: " + kind)
    ports = modules["billet_t3_top"]["ports"]
    require(set(ports) == set(PORTS), "Top port set mismatch")
    for name, (direction, width, signed) in PORTS.items():
        p = ports[name]
        require((p["direction"], len(p["bits"]), bool(p.get("signed", 0))) ==
                (direction, width, signed), "Port shape/signedness: " + name)
    memories, multipliers = [], []
    for name, module in modules.items():
        require(not int(module.get("attributes", {}).get("blackbox", "0"), 2),
                "Blackbox module " + name)
        for cellname, cell in module["cells"].items():
            require("latch" not in cell["type"].lower(), "Latch in structural netlist")
            if cell["type"] == "$mem_v2":
                p = cell["parameters"]
                width, size = int(p["WIDTH"], 2), int(p["SIZE"], 2)
                memories.append({"module": name, "cell": cellname,
                                 "width": width, "words": size, "bits": width*size})
            if cell["type"] == "$mul":
                multipliers.append(name + "." + cellname)
    require(sum(m["bits"] for m in memories
                if m["module"] == "billet_t3_channel_buf") >= 4*256*32,
            "Four raw ring storage capacity missing")
    require(sum(m["bits"] for m in memories
                if m["module"] == "billet_t3_fft_core") >= 256*(32+36),
            "Transform storage capacity missing")
    require(any("window." in m for m in multipliers), "Window multiplication not synthesized")
    require(any("power_spectrum." in m for m in multipliers), "Power multiplication absent")
    if probe:
        return {"outcome": "passed", "scope": "bounded structural preparation only",
                "memories_before_mapping": memories, "reachable_multipliers": multipliers,
                "raw_stdout": str(stdout.relative_to(ROOT))}
    gates = json.loads(netlist.read_text())["modules"]
    cells = Counter(c["type"] for m in gates.values() for c in m["cells"].values())
    require(sum(cells.values()) > 1000, "Implausibly empty generic synthesized design")
    for kind in cells:
        require("latch" not in kind.lower(), "Latch after synthesis")
        require(not kind.startswith("$") or kind.startswith("$_") or kind in gates,
                "Unmapped high-level cell after generic synthesis: " + kind)
    return {"outcome": "passed", "scope": "generic technology-independent synthesis, no ABC",
            "hierarchy": expected_children, "ports_checked": len(PORTS),
            "memories_before_mapping": memories, "reachable_multipliers": multipliers,
            "generic_cell_types": dict(cells), "raw_stdout": str(stdout.relative_to(ROOT)),
            "structural_json": str(structural.relative_to(ROOT)),
            "netlist_json": str(netlist.relative_to(ROOT))}


def source_delivery():
    names = ["top", "channel_buf", "window", "power_spectrum", "fft_core",
             "bitrev", "twiddle_rom", "butterfly", "bfp_scaler"]
    for name in names:
        path = ROOT / "rtl" / ("billet_t3_" + name + ".sv")
        require(path.is_file(), "Missing delivered module: " + str(path))
        text = path.read_text()
        require(re.search(r"\bmodule\s+billet_t3_" + name + r"\b", text),
                "Expected module declaration missing")
        require("billet_t2_" not in text, "Delivered hardware depends on Gen-2")
        require(not re.search(r"\$(readmem|system)|\breal\b|translate_off", text),
                "Simulation-only source construct in delivery")
    for doc in ("SPEC.md", "ARCHITECTURE.md"):
        require((ROOT / "design" / doc).stat().st_size > 1000, "Missing substantive " + doc)
    header = (ROOT / "rtl/billet_t3_top.sv").read_text().split(");", 1)[0]
    require("parameter" not in header, "Unexpected public structural parameters")
    chunks = re.split(r"\b(input|output)\s+wire\s+", header)[1:]
    found = {}
    for direction, clause in zip(chunks[::2], chunks[1::2]):
        match = re.match(r"(signed\s+)?(?:\[(\d+):0\]\s*)?(.+)", clause, re.S)
        require(match is not None, "Unrecognized port declaration")
        signed, high, rest = match.groups()
        width = int(high) + 1 if high else 1
        for name in rest.strip().strip(",").split(","):
            found[name.strip()] = (direction, width, bool(signed))
    require(found == PORTS, "Delivered public port contract")
    core_header = (ROOT / "rtl/billet_t3_fft_core.sv").read_text().split(");", 1)[0]
    reference_header = (ROOT / "billet_t2_reference/rtl/billet_t2_top.sv"
                        ).read_text().split(");", 1)[0].replace(
                            "billet_t2_top", "billet_t3_fft_core")
    require(re.sub(r"\s+", "", core_header) == re.sub(r"\s+", "", reference_header),
            "Core ports differ from mounted Gen-2 directions/widths/signedness")
    return {"module_files": len(names), "public_ports": len(PORTS),
            "source_selectors": ["rtl/*.sv", "design/SPEC.md", "design/ARCHITECTURE.md",
                                 "tests/*.py", "billet_t2_reference/rtl/*.sv"]}


def delivery(run, probe=False):
    result = source_delivery()
    s = scenarios.Scenario("source-only-reproduction", isolated=True)
    s.send([(16384, -8192)] + [(0, 0)] * 15, ch=3)
    s.drain()
    # Use the check's retained source snapshot, not an existing build or binary.
    copied = sorted((run.directory / "sources/rtl").glob("*.sv"))
    trace = simulate(run, s, rtl=copied)
    result["source_only_reproduction"] = Scoreboard(s).compare(trace)
    private = run.directory / "private-defect"
    private.mkdir()
    for source in copied:
        text = source.read_text()
        if source.name == "billet_t3_power_spectrum.sv":
            text, changes = re.subn(r"assign out_power\s*=\s*[^;]+;",
                                   "assign out_power = 32'd0;", text)
            require(changes == 1, "Private defect mutation did not target exact assignment")
        (private / source.name).write_text(text)
    failed_trace = simulate(run, s, rtl=sorted(private.glob("*.sv")), suffix="-private-defect")
    try:
        Scoreboard(s).compare(failed_trace)
    except AssertionError as e:
        require("Power mismatch" in str(e), "Private defect failed for unintended reason")
        result["defect_sensitivity"] = {
            "outcome": "expected_checker_rejection", "diagnostic": str(e),
            "simulator_exit": 0, "defect": "Private copied power output stuck at zero",
            "raw_trace": str(failed_trace.relative_to(ROOT)),
            "production_sources_modified": False}
        write(run.directory / "expected-defect-rejection.json", result["defect_sensitivity"])
    else:
        raise AssertionError("Public transaction scoreboard accepted intentional power defect")
    # Re-execute unchanged accepted sources after the disposable negative check.
    if not probe:
        good = simulate(run, s, rtl=copied, suffix="-restored")
        result["unchanged_source_rerun"] = Scoreboard(s).compare(good)
        require(trace.read_bytes() == good.read_bytes(), "Unchanged source reproduction differed")
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", choices=("behavior", "synthesis", "delivery"), required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--probe", action="store_true",
                        help="bounded advisory subset; never an admitted passing check")
    parser.add_argument("--repair-of")
    parser.add_argument("--probe-focus", choices=("arithmetic", "streams"),
                        default="arithmetic")
    args = parser.parse_args()
    output = (ROOT / args.output).resolve()
    require(output.is_relative_to(ROOT / "evidence"), "Outputs must remain project-local evidence")
    if args.probe:
        require(output.is_relative_to(ROOT / "evidence/preparation"),
                "Advisory diagnostics belong under evidence/preparation")
    require(args.probe or args.probe_focus == "arithmetic",
            "--probe-focus is available only for advisory diagnostics")
    run = Run(output / ("run-" + stamp().replace(":", "").replace("+", "") +
                        "-" + uuid.uuid4().hex[:8]), [sys.executable, *sys.argv], args.repair_of)
    try:
        run.version("python3")
        for tool in (("yosys",) if args.check == "synthesis" else ("iverilog", "vvp")):
            run.version(tool)
        if args.check == "behavior":
            if args.probe and args.probe_focus == "streams":
                result = {"scope": "bounded streaming preparation", "runs": []}
                for scenario in [scenarios.overlap(True), scenarios.boundaries(),
                                 scenarios.buffer()]:
                    trace = simulate(run, scenario)
                    result["runs"].append(Scoreboard(scenario).compare(trace))
                    write(run.directory / f"stream-results-{len(result['runs'])}.json", result)
            else:
                result = behavior(run, args.probe)
        elif args.check == "synthesis":
            result = synthesis(run, args.probe)
        else:
            result = delivery(run, args.probe)
        require(hashes() == run.receipt["source_sha256"],
                "Sources changed during tool execution; results cannot be admitted")
        run.finish("passed", result=result)
    except Exception as e:
        run.finish("failed", result=run.result, error=f"{type(e).__name__}: {e}")
        print(f"FAILED: {e}; receipt={run.directory.relative_to(ROOT)}/receipt.json",
              file=sys.stderr)
        return 1
    print(json.dumps({"status": "passed", "check": args.check,
                      "preparation_only": args.probe,
                      "receipt": str((run.directory / "receipt.json").relative_to(ROOT))}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
