#!/usr/bin/env python3
"""BILLET-T1 independent executable acceptance matrix (standard library only).

Requirements -> checks:
  numerical equations / telemetry -> fft_integer, butterfly unit, every frame
  coefficients / permutation -> exhaustive public-port units, N=2..256
  framing / latency / stalls / reset -> every-cycle public-pin transaction trace
  address coverage / port separation -> standalone scheduler public-port trace
  quality -> independent direct DFT, per-frame cosine >= .999 and SQNR >= 30 dB
  sensitivity -> four disposable RTL mutations, unchanged numerical expectations
  synthesizability -> real Yosys for 2,16,64,256; structural JSON assertions

Quality amplitudes are chosen here, before simulation: impulses 30000+j12000,
DC 12000+j7000, tones radius 20000, multitone radii 9000/6000/4000,
random components in [-16000,16000]. Zero/low/clipped stress never substitutes
for these adequately excited quality frames. No scientific package is used.
Default invocation includes behavior, mutations AND synthesis.
"""

import argparse
import cmath
import hashlib
import json
import math
from pathlib import Path
import random
import re
import shutil
import subprocess
import sys
import time
import traceback
import uuid


ROOT = Path(__file__).resolve().parents[1]
RTL_NAMES = [
    "billet_t1_pkg.sv", "billet_t1_twiddle_rom.sv", "billet_t1_bitrev.sv",
    "billet_t1_butterfly.sv", "billet_t1_buffer_sched.sv", "billet_t1_top.sv",
]
SIZES = (2, 16, 64, 256)
SEED = 0xB111E701
TIMEOUT = 3600


class VerificationFailure(AssertionError):
    pass


class NumericalMismatch(VerificationFailure):
    pass


def require(condition, message):
    if not condition:
        raise VerificationFailure(message)


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def clamp(x):
    return max(-32768, min(32767, x))


def round_away(x):
    return math.floor(x + .5) if x >= 0 else math.ceil(x - .5)


def coefficient(n, k):
    angle = 2 * math.pi * k / n
    return clamp(round_away(32768 * math.cos(angle))), clamp(round_away(-32768 * math.sin(angle)))


def butterfly(a, b, w):
    tr = (b[0] * w[0] - b[1] * w[1]) // 32768
    ti = (b[0] * w[1] + b[1] * w[0]) // 32768
    raw = [(a[0] + tr) // 2, (a[1] + ti) // 2,
           (a[0] - tr) // 2, (a[1] - ti) // 2]
    return (clamp(raw[0]), clamp(raw[1])), (clamp(raw[2]), clamp(raw[3])), sum(x != clamp(x) for x in raw)


def fft_integer(samples):
    """Specification-derived unbounded integer model; no RTL data is imported."""
    n = len(samples)
    width = n.bit_length() - 1
    values = [samples[int(f"{i:0{width}b}"[::-1], 2)] for i in range(n)]
    increments = []
    for s in range(width):
        half = 1 << s
        for base in range(0, n, 2 * half):
            for j in range(half):
                a, b = base + j, base + j + half
                values[a], values[b], inc = butterfly(values[a], values[b], coefficient(n, j * n // (2 * half)))
                increments.append(inc)
    return values, increments


def dft_float(samples):
    n = len(samples)
    # Deliberately direct O(N^2) DFT, not another radix-2 implementation.
    return [sum(complex(*x) * cmath.exp(-2j * math.pi * k * i / n)
                for i, x in enumerate(samples)) / n for k in range(n)]


def quality_metrics(samples, result):
    reference = dft_float(samples)
    expected = [c for x in reference for c in (x.real, x.imag)]
    actual = [c for x in result for c in x]
    error = [x - y for x, y in zip(actual, expected)]
    signal = sum(x * x for x in expected)
    observed = sum(x * x for x in actual)
    noise = sum(x * x for x in error)
    return {
        "cosine": sum(x * y for x, y in zip(actual, expected)) / math.sqrt(signal * observed)
        if signal and observed else None,
        "sqnr_db": 10 * math.log10(signal / noise) if signal and noise else None,
        "sqnr_exact": bool(signal and not noise),
        "max_abs_error_codes": max(map(abs, error)),
        "rmse_codes": math.sqrt(noise / len(error)),
        "reference_energy": signal,
    }


def frames(n):
    rng = random.Random(SEED + n)
    cases = []

    def add(name, data, quality=False):
        require(len(data) == n and all(-32768 <= c <= 32767 for x in data for c in x), name)
        cases.append({"name": name, "input": data, "quality_required": quality and n >= 16})

    add("zero", [(0, 0)] * n)
    add("low_level", [(i % 3 - 1, (i * 7) % 5 - 2) for i in range(n)])
    for position in sorted({0, 1, n // 3, n - 1}):
        data = [(0, 0)] * n
        data[position] = (30000, 12000)
        add(f"impulse_{position}", data, True)
    for sign in (1, -1):
        add(f"dc_{sign}", [(sign * 12000, sign * 7000)] * n, True)
    for k in sorted({1, max(1, n // 7), n // 2 - 1}):
        if k <= 0:
            continue
        add(f"tone_{k}", [(round_away(20000 * math.cos(2 * math.pi * k * i / n)),
                          round_away(20000 * math.sin(2 * math.pi * k * i / n))) for i in range(n)], True)
    add("multitone", [(round_away(sum(a * math.cos(2 * math.pi * k * i / n + p)
                                     for a, k, p in ((9000, 1, .2), (6000, 3, -.7), (4000, n // 2 - 1, .9)))),
                       round_away(sum(a * math.sin(2 * math.pi * k * i / n + p)
                                     for a, k, p in ((9000, 1, .2), (6000, 3, -.7), (4000, n // 2 - 1, .9)))))
                      for i in range(n)], True)
    for seed_index in range(3):
        add(f"random_safe_{seed_index}", [(rng.randint(-16000, 16000), rng.randint(-16000, 16000)) for _ in range(n)], True)
    add("high_amplitude_safe", [(30000, -7000)] * n, True)
    add("asymmetric", [((i * 7919 + 71) % 40001 - 20000, (i * 3571 + 999) % 42001 - 21000) for i in range(n)])
    add("mutation_discriminator", [(rng.randint(-512, 512), rng.randint(-512, 512)) for _ in range(n)])
    add("full_square_corners", [(rng.choice((-32768, 32767)), rng.choice((-32768, 32767))) for _ in range(n)])
    add("full_square_random", [(rng.randint(-32768, 32767), rng.randint(-32768, 32767)) for _ in range(n)])
    for corner in ((-32768, -32768), (-32768, 32767), (32767, -32768), (32767, 32767)):
        add(f"constant_corner_{corner[0]}_{corner[1]}", [corner] * n)
    if n >= 16:
        data = [(0, 0)] * n
        for index, value in {0: (-32768, -32768), 2: (-32768, -32768),
                             8: (32767, 32767), 10: (32767, 32767),
                             4: (32767, -32768), 6: (32767, -32768),
                             12: (-32768, 32767), 14: (-32768, 32767)}.items():
            data[index * (n // 16)] = value
        add("directed_clipping_counterexample", data)
    return cases


def oracle_preflight(evidence):
    """Check matrix feasibility without using any RTL outputs or coefficients."""
    metrics = []
    for n in SIZES:
        for case in frames(n):
            result, increments = fft_integer(case["input"])
            quality = quality_metrics(case["input"], result)
            if case["quality_required"]:
                require(sum(increments) == 0, f"preselected quality amplitude clips: N={n} {case['name']}")
                require(quality["cosine"] is not None and quality["cosine"] >= .999 and
                        (quality["sqnr_exact"] or quality["sqnr_db"] is not None and quality["sqnr_db"] >= 30),
                        f"preselected quality frame infeasible: N={n} {case['name']} {quality}")
            if case["name"] == "directed_clipping_counterexample":
                require(sum(increments) > 0, f"counterexample did not clip at N={n}")
            metrics.append({"n": n, "name": case["name"], "quality_required": case["quality_required"],
                            "clamp_events": sum(increments), **quality})
    evidence.metrics.append({"check": "independent_oracle_preflight", "cases": metrics})
    evidence.save()


class Evidence:
    def __init__(self, check, preparation=False, repair_of=None):
        category = "preparation" if preparation else "verification"
        self.folder = ROOT / "evidence" / category / (time.strftime("%Y%m%dT%H%M%SZ", time.gmtime()) + "-" + check + "-" + uuid.uuid4().hex[:10])
        self.folder.mkdir(parents=True)
        self.started = time.time()
        self.commands = []
        self.versions = {}
        self.metrics = []
        self.hashes = {}
        for pattern in ("rtl/*.sv", "design/*.md", "tests/*.py"):
            for source in sorted(ROOT.glob(pattern)):
                relative = source.relative_to(ROOT)
                self.hashes[str(relative)] = digest(source)
                target = self.folder / "sources" / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(source, target)
        self.receipt = {
            "schema": 1, "check": check, "argv": [sys.executable, *sys.argv],
            "cwd": str(ROOT), "started_at": self.started,
            "timeout_s": TIMEOUT, "source_hashes": self.hashes,
            "seed": SEED, "repair_of": repair_of, "commands": self.commands,
            "tool_versions": self.versions, "metrics": self.metrics,
            "stdout": str((self.folder / "stdout.log").relative_to(ROOT)),
            "stderr": str((self.folder / "stderr.log").relative_to(ROOT)),
        }
        (self.folder / "stdout.log").touch()
        (self.folder / "stderr.log").touch()
        self.save()

    def save(self):
        (self.folder / "receipt.json").write_text(json.dumps(self.receipt, indent=2, allow_nan=False) + "\n")

    def execute(self, argv, folder, stem, expected_success=True):
        folder.mkdir(parents=True, exist_ok=True)
        stdout, stderr = folder / (stem + ".stdout"), folder / (stem + ".stderr")
        record = {"argv": list(map(str, argv)), "cwd": str(folder), "started_at": time.time(),
                  "timeout_s": TIMEOUT, "stdout": str(stdout.relative_to(ROOT)),
                  "stderr": str(stderr.relative_to(ROOT))}
        self.commands.append(record)
        self.save()
        try:
            with stdout.open("w") as out, stderr.open("w") as err:
                process = subprocess.run(record["argv"], cwd=folder, stdout=out, stderr=err, timeout=TIMEOUT, check=False)
            record.update(exit_code=process.returncode, timed_out=False)
        except subprocess.TimeoutExpired:
            record.update(exit_code=None, timed_out=True)
            raise VerificationFailure(f"tool timeout: {record['argv']}; {stdout.relative_to(ROOT)}")
        except OSError as exc:
            record.update(exit_code=None, timed_out=False, launch_error=str(exc))
            raise VerificationFailure(f"tool launch failure: {record['argv']}: {exc}") from exc
        finally:
            record["ended_at"] = time.time()
            self.save()
        if expected_success:
            require(process.returncode == 0, f"tool failed ({process.returncode}): {record['argv']}; see {stderr.relative_to(ROOT)}")
        return process.returncode, stdout.read_text(), stderr.read_text()

    def tools(self, names):
        for tool in names:
            require(shutil.which(tool), f"required installed tool unavailable: {tool}")
            argv = [tool, "--version"] if tool == "python3" else [tool, "-V"]
            _, out, err = self.execute(argv, self.folder / "versions", tool, expected_success=False)
            self.versions[tool] = (out + err).strip()
        self.save()

    def finish(self, failure=None):
        for name, old_hash in self.hashes.items():
            require(digest(ROOT / name) == old_hash, f"accepted source changed during check: {name}")
        self.receipt.update(ended_at=time.time(), exit_code=1 if failure else 0,
                            status="failed" if failure else "passed", failure=failure, timed_out=False)
        self.save()


def compile_sim(evidence, folder, text, sources=None, top="tb"):
    folder.mkdir(parents=True, exist_ok=True)
    bench = folder / "bridge.sv"
    bench.write_text(text)
    source_paths = sources or [ROOT / "rtl" / x for x in RTL_NAMES]
    evidence.execute(["iverilog", "-g2012", "-Wall", "-s", top, "-o", folder / "sim.vvp",
                      *source_paths, bench], folder, "compile")
    _, output, _ = evidence.execute(["vvp", folder / "sim.vvp"], folder, "simulate")
    finish_notice = re.compile(re.escape(str(bench)) + r":\d+: \$finish called at \d+ \([^)]+\)")
    return "\n".join(line for line in output.splitlines() if not finish_notice.fullmatch(line)) + "\n"


PUBLIC = ("in_ready", "out_valid", "out_last", "frame_done", "out_re", "out_im",
          "out_bin_idx", "saturation_count", "overflow_flag")
SCHED = ("load_we", "stage_read", "stage_write", "output_fetch", "src_bank",
         "dst_bank", "load_addr", "addr_a", "addr_b", "twiddle_addr",
         "output_addr", "stage_idx")


class Traffic:
    """Public transaction/timestamp oracle; no hierarchical DUT observations."""
    def __init__(self, n, seed):
        self.n, self.log = n, n.bit_length() - 1
        self.rng = random.Random(seed)
        self.rows, self.expectations, self.completed = [], [], []
        self.coverage = {name: 0 for name in ("input_gap", "busy_demand", "stall_first", "stall_final",
                                             "stall_middle", "done", "reset_load", "reset_compute",
                                             "reset_stalled_output", "early_last", "missing_last")}
        self.cycle = 0
        self.reset = True
        self.held_input = None
        self.clear()

    def clear(self):
        self.inputs = []
        self.final_edge = None
        self.next_valid = None
        self.output_index = 0
        self.valid = False
        self.done = False
        self.saturation = 0
        self.active = None
        self.results = []
        self.increments = []

    def public(self):
        if self.reset:
            return [0] * len(PUBLIC)
        ready = int(self.final_edge is None and not self.valid)
        payload = self.results[self.output_index] if self.valid else (0, 0)
        return [ready, int(self.valid), int(self.valid and self.output_index == self.n - 1),
                int(self.done), *payload, self.output_index if self.valid else 0,
                self.saturation, int(self.saturation != 0)]

    def scheduler(self):
        if self.reset:
            return [0] * len(SCHED)
        if self.final_edge is None:
            return [0, 0, 0, 0, 0 if self.active is None else self.log % 2,
                    1 if self.active is None else 1 - self.log % 2,
                    len(self.inputs), 0, 1, 0, 0, 0]
        offset = self.cycle - self.final_edge
        if offset < self.n * self.log:
            stage, within = divmod(offset, self.n)
            q = within // 2
            half = 1 << stage
            base = (q // half) * (2 * half)
            j = q % half
            return [0, int(within % 2 == 0), int(within % 2 == 1), 0,
                    stage % 2, 1 - stage % 2, 0, base + j, base + j + half,
                    j * self.n // (2 * half), 0, stage]
        # After computation the scheduler retains the last stage and q=0.
        stage = self.log - 1
        return [0, 0, 0, int(not self.valid), self.log % 2, 1 - self.log % 2,
                0, 0, 1 << stage, 0, self.output_index, stage]

    def step(self, valid=0, re_part=0, im_part=0, last=0, ready=1, reset=False):
        self.reset = reset
        if reset:
            self.clear()
        pre = self.public()
        offered = (valid, re_part, im_part, last)
        if not reset and self.held_input is not None:
            require(offered == self.held_input, f"test source violated held input at cycle {self.cycle}")
        self.held_input = offered if not reset and valid and not pre[0] else None
        schedule = self.scheduler()
        schedule[0] = int(not reset and valid and pre[0])
        self.rows.append((int(not reset), valid, last, re_part, im_part, ready))
        self.expectations.append((pre, schedule))
        edge = self.cycle + 1
        self.done = False
        if not reset:
            if valid and not pre[0]:
                self.coverage["busy_demand"] += 1
            if pre[0] and not valid:
                self.coverage["input_gap"] += 1
            if pre[0] and valid:
                self.inputs.append((re_part, im_part))
                if last and len(self.inputs) != self.n:
                    self.coverage["early_last"] += 1
                if len(self.inputs) == self.n:
                    if not last:
                        self.coverage["missing_last"] += 1
                    self.final_edge = edge
                    self.results, self.increments = fft_integer(self.inputs)
                    self.next_valid = edge + self.n * self.log + 1
                    self.output_index = 0
            elif pre[1]:
                if not ready:
                    key = "stall_first" if self.output_index == 0 else "stall_final" if self.output_index == self.n - 1 else "stall_middle"
                    self.coverage[key] += 1
                else:
                    self.valid = False
                    if self.output_index == self.n - 1:
                        self.completed.append({"input": list(self.inputs), "expected": list(self.results),
                                               "saturation_count": self.saturation, "final_input_edge": self.final_edge,
                                               "done_edge": edge, "name": self.active["name"] if self.active else "unnamed"})
                        self.final_edge = None
                        self.next_valid = None
                        self.inputs = []
                        self.output_index = 0
                        self.done = True
                        self.coverage["done"] += 1
                    else:
                        self.output_index += 1
                        self.next_valid = edge + 1
            if self.final_edge is not None:
                offset = edge - self.final_edge
                if 2 <= offset <= self.n * self.log and offset % 2 == 0:
                    self.saturation = min(0xffffffff, self.saturation + self.increments[offset // 2 - 1])
                if edge == self.next_valid:
                    self.valid = True
        self.cycle = edge
        self.expectations[-1] += (self.public(),)

    def run_frame(self, case, mode, pending=(117, -991), pending_last=0):
        self.active = case
        start_completed = len(self.completed)
        for i, (real, imag) in enumerate(case["input"]):
            if mode == "random" and i > 0:
                for _ in range(self.rng.randrange(4)):
                    self.step(ready=self.rng.randrange(2))
            last = int(i == self.n - 1)
            if mode == "early_last":
                last = int(i in (0, self.n // 2, self.n - 1))
            if mode == "missing_last":
                last = 0
            self.step(1, real, imag, last, ready=1)
        stalls = {}
        bound = self.n * self.log + self.n * 50 + 200
        for _ in range(bound):
            ready = 1
            if mode != "no_stall":
                if self.valid:
                    index = self.output_index
                    duration = 29 if index in (0, self.n - 1) else 3
                    used = stalls.get(index, 0)
                    if used < duration or self.rng.random() < .25:
                        ready = 0
                        stalls[index] = used + 1
                else:
                    ready = self.rng.randrange(2)
            self.step(1, *pending, pending_last, ready)
            if len(self.completed) != start_completed:
                break
        require(len(self.completed) == start_completed + 1, f"cycle bound / no completion N={self.n} {case['name']}")
        record = self.completed[-1]
        record.update(quality_required=case["quality_required"], traffic=mode)
        if mode == "no_stall":
            require(record["done_edge"] == record["final_input_edge"] + self.n * self.log + 2 * self.n,
                    "oracle schedule error")


def make_traffic(n, cases):
    traffic = Traffic(n, SEED + n)
    traffic.step(reset=True)
    traffic.step(reset=True)
    for index, case in enumerate(cases):
        mode = ("no_stall", "random", "early_last", "missing_last")[index % 4]
        next_sample = cases[(index + 1) % len(cases)]["input"][0]
        next_mode = ("no_stall", "random", "early_last", "missing_last")[(index + 1) % 4]
        traffic.run_frame(case, mode, next_sample, int(next_mode == "early_last"))
    # All reset-abort epochs use public transactions; held inputs never change
    # while reset is inactive and a previous offered beat remains unaccepted.
    for phase in ("load", "compute", "stalled_output"):
        traffic.step(reset=True)
        data = cases[-1]["input"]
        count = max(1, n // 2) if phase == "load" else n
        for i, sample in enumerate(data[:count]):
            traffic.step(1, *sample, int(i == n - 1))
        if phase == "compute":
            for _ in range(max(1, n * traffic.log // 2)):
                traffic.step(1, 117, -991, ready=0)
            require(traffic.final_edge is not None and not traffic.valid, "compute reset precondition")
        if phase == "stalled_output":
            while not traffic.valid:
                traffic.step(1, 117, -991, ready=0)
            for _ in range(17):
                traffic.step(1, 117, -991, ready=0)
            require(traffic.public()[1] == 1, "stalled reset precondition")
        traffic.coverage["reset_" + phase] += 1
        traffic.step(1, 117, -991, ready=0, reset=True)
        traffic.step(reset=True)
        recovery = dict(cases[3], name="recovery_after_" + phase)
        traffic.run_frame(recovery, "random")
    traffic.step(reset=True)
    traffic.step()
    for _ in range(n * traffic.log + 2 * n + 5):
        traffic.step()
    return traffic


def bridge(n):
    width = n.bit_length() - 1
    stage_width = max(1, (width - 1).bit_length())
    public_args = ", ".join(["in_ready", "out_valid", "out_last", "frame_done",
                             "$signed(out_re)", "$signed(out_im)", "out_bin_idx",
                             "saturation_count", "overflow_flag"])
    schedule_args = ", ".join(SCHED)
    return f"""
module tb;
  reg clk=0, rst_n=0, in_valid=0, in_last=0, out_ready=0;
  reg signed [15:0] in_re=0, in_im=0;
  wire in_ready,out_valid,out_last,frame_done,overflow_flag;
  wire signed [15:0] out_re,out_im;
  wire [{width-1}:0] out_bin_idx;
  wire [31:0] saturation_count;
  billet_t1_top #(.N_POINTS({n})) dut(.*);
  wire load_we,stage_read,stage_write,output_fetch,src_bank,dst_bank;
  wire [{width-1}:0] load_addr,addr_a,addr_b,twiddle_addr,output_addr,s_idx;
  wire [{stage_width-1}:0] stage_idx;
  wire s_ready,s_valid,s_last,s_done;
  billet_t1_buffer_sched #(.N_POINTS({n})) scheduler(
    .clk(clk),.rst_n(rst_n),.in_valid(in_valid),.out_ready(out_ready),
    .in_ready(s_ready),.out_valid(s_valid),.out_last(s_last),.frame_done(s_done),
    .out_bin_idx(s_idx),.load_we(load_we),.stage_read(stage_read),
    .stage_write(stage_write),.output_fetch(output_fetch),.src_bank(src_bank),
    .dst_bank(dst_bank),.load_addr(load_addr),.addr_a(addr_a),.addr_b(addr_b),
    .twiddle_addr(twiddle_addr),.output_addr(output_addr),.stage_idx(stage_idx));
  integer fd,rc,i=0,r,v,l,rr,ii,o;
  task check_reset;
    begin
      if ({{in_ready,out_valid,out_last,frame_done,overflow_flag,out_re,out_im,
            out_bin_idx,saturation_count}} !== 0) $fatal(1,"RESET_OUTPUT_X_OR_NONZERO");
    end
  endtask
  always @(posedge clk or negedge clk) if (!rst_n) check_reset;
  initial begin
    // Reset is asserted at time zero, not manufactured with a 1->0 pulse.
    #1; check_reset;
    #4; clk=1; check_reset;
    #5; clk=0;
    fd=$fopen("stimulus.txt","r");
    if (!fd) $fatal(1,"missing stimulus");
    while (!$feof(fd)) begin
      rc=$fscanf(fd,"%d %d %d %d %d %d\\n",r,v,l,rr,ii,o);
      if (rc != 6) $fatal(1,"malformed stimulus");
      #1; rst_n=r; in_valid=v; in_last=l; in_re=rr; in_im=ii; out_ready=o;
      #2;
      if (!rst_n) check_reset;
      $display("T %0d P %0d %0d %0d %0d %0d %0d %0d %0d %0d",i,{public_args});
      $display("S %0d %0d %0d %0d %0d %0d %0d %0d %0d %0d %0d %0d %0d",i,{schedule_args});
      if ({{s_ready,s_valid,s_last,s_done,s_idx}} !==
          {{in_ready,out_valid,out_last,frame_done,out_bin_idx}}) $fatal(1,"scheduler public disagreement");
      #2; clk=1;
      #1;
      $display("T %0d Q %0d %0d %0d %0d %0d %0d %0d %0d %0d",i,{public_args});
      #4; clk=0;
      $display("T %0d N %0d %0d %0d %0d %0d %0d %0d %0d %0d",i,{public_args});
      i=i+1;
    end
    $fclose(fd);
    $display("END %0d",i);
    $finish;
  end
endmodule
"""


def parse_trace(text, traffic, n):
    lines = text.splitlines()
    require(len(lines) == 4 * len(traffic.rows) + 1, f"missing/extra trace rows N={n}: {len(lines)}")
    outputs = []
    scheduler_coverage = {}
    numeric_differences = []
    for index, (pre, sched, post) in enumerate(traffic.expectations):
        for relative, marker, expected in ((0, "P", pre), (2, "Q", post), (3, "N", post)):
            tokens = lines[index * 4 + relative].split()
            require(tokens[:3] == ["T", str(index), marker] and len(tokens) == 12,
                    f"malformed public trace {index} {marker}")
            require(all(re.fullmatch(r"-?\d+", token) for token in tokens[3:]),
                    f"active X/Z or invalid public value {index} {marker}: {tokens}")
            actual = list(map(int, tokens[3:]))
            if actual[1] and expected[1] and actual[4:6] != expected[4:6]:
                raise NumericalMismatch(f"N={n} cycle={index} {marker} bin={expected[6]} "
                                        f"actual={actual[4:6]} expected={expected[4:6]}")
            for field, got, want in zip(PUBLIC, actual, expected):
                if got != want:
                    if field in ("out_re", "out_im"):
                        numeric_differences.append({"cycle": index, "edge": marker, "field": field, "actual": got, "expected": want})
                    else:
                        require(False, f"protocol/telemetry mismatch N={n} cycle={index} {marker} {field}: {got} != {want}")
            if marker == "P" and pre[1] and traffic.rows[index][-1]:
                outputs.append((actual[4], actual[5]))
        tokens = lines[index * 4 + 1].split()
        require(tokens[:2] == ["S", str(index)] and len(tokens) == 14 and
                all(re.fullmatch(r"\d+", token) for token in tokens[2:]),
                f"malformed/XZ scheduler trace cycle {index}")
        actual_schedule = list(map(int, tokens[2:]))
        # LOAD after completion retains stage and source ownership. Its idle
        # addresses are not effective memory accesses and need not be compared.
        for field, got, want in zip(SCHED[:4], actual_schedule[:4], sched[:4]):
            require(got == want, f"scheduler enable {field} cycle={index}: {got}!={want}")
        if any(sched[:4]):
            effective = (6,) if sched[0] else (4, 5, 10) if sched[3] else (4, 5, 7, 8, 9, 11)
            for pos in effective:
                require(actual_schedule[pos] == sched[pos],
                        f"scheduler {SCHED[pos]} N={n} cycle={index}: {actual_schedule[pos]} != {sched[pos]}")
        if sched[1] or sched[2]:
            _, read, write, _, source, dest, _, a, b, k, _, stage = actual_schedule
            require(source != dest and a != b and 0 <= a < n and 0 <= b < n and 0 <= k < n // 2,
                    "bank conflict/address bounds")
            key = (stage, "read" if read else "write")
            scheduler_coverage.setdefault(key, []).extend((a, b))
    require(lines[-1] == f"END {len(traffic.rows)}", "missing completion trace")
    if numeric_differences:
        raise NumericalMismatch(f"{len(numeric_differences)} scalar trace mismatches; first={numeric_differences[0]}")
    expected_outputs = [sample for case in traffic.completed for sample in case["expected"]]
    # Aborted output is deliberately stalled at bin zero, so none was accepted.
    require(outputs == expected_outputs, "output acceptance conservation/order")
    for stage in range(traffic.log):
        for phase in ("read", "write"):
            visits = scheduler_coverage.get((stage, phase), [])
            require(visits and set(visits) == set(range(n)), f"missing stage address coverage {stage} {phase}")
    return outputs, {"scalar_bit_mismatches": 0, "accepted_outputs": len(outputs),
                     "cycles": len(traffic.rows), "coverage": traffic.coverage,
                     "scheduler_addresses": {f"{s}_{p}": len(v) for (s, p), v in scheduler_coverage.items()}}


def behavior_cell(evidence, n, cases=None, sources=None, tag=None, require_coverage=True):
    cases = cases or frames(n)
    traffic = make_traffic(n, cases)
    folder = evidence.folder / (tag or f"behavior-N{n}")
    folder.mkdir(parents=True)
    (folder / "stimulus.txt").write_text("".join(" ".join(map(str, row)) + "\n" for row in traffic.rows))
    (folder / "cases.json").write_text(json.dumps(cases, indent=2) + "\n")
    output = compile_sim(evidence, folder, bridge(n), sources)
    actual, metric = parse_trace(output, traffic, n)
    if require_coverage:
        for key, value in traffic.coverage.items():
            # N=2 has no middle bin.
            require(value > 0 or (key == "stall_middle" and n == 2), f"coverage not observed N={n}: {key}")
    metric.update(check="behavior", n=n, seed=SEED + n, frames=[])
    offset = 0
    for case in traffic.completed:
        result = actual[offset:offset + n]
        offset += n
        quality = quality_metrics(case["input"], result)
        _, incs = fft_integer(case["input"])
        clips = sum(incs)
        if case["quality_required"]:
            require(clips == 0, f"quality frame not rail-safe: N={n} {case['name']}")
            require(quality["cosine"] is not None and quality["cosine"] >= .999,
                    f"cosine below .999: N={n} {case['name']} {quality}")
            require(quality["sqnr_exact"] or quality["sqnr_db"] is not None and quality["sqnr_db"] >= 30,
                    f"SQNR below 30dB: N={n} {case['name']} {quality}")
        if case["name"] == "directed_clipping_counterexample":
            require(clips > 0, "directed full-scale case did not actually clip")
        metric["frames"].append({key: case[key] for key in ("name", "traffic", "quality_required", "final_input_edge", "done_edge")} |
                                {"clamp_events": clips, "sticky_saturation_count": case["saturation_count"], **quality})
    evidence.metrics.append(metric)
    evidence.save()
    return metric


def units(evidence):
    # Exhaustive coefficient and bit-reversal public-port comparison for every
    # supported power of two, not a textual ROM comparison.
    for n in (2, 4, 8, 16, 32, 64, 128, 256):
        a = n.bit_length() - 1
        text = f"""
module tb;
reg [{a-1}:0] idx=0,k=0;
wire [{a-1}:0] rev_idx;
wire signed [15:0] w_re,w_im;
billet_t1_bitrev #(.N_POINTS({n})) b(.*);
billet_t1_twiddle_rom #(.N_POINTS({n})) w(.*);
integer i;
initial begin
 for(i=0;i<{n};i=i+1) begin
  idx=i; k=i%{n//2}; #1;
  $display("U %0d %0d %0d %0d",i,rev_idx,$signed(w_re),$signed(w_im));
 end
 $finish;
end
endmodule
"""
        output = compile_sim(evidence, evidence.folder / f"units-N{n}", text)
        lines = output.splitlines()
        require(len(lines) == n, f"unit row count N={n}")
        for i, line in enumerate(lines):
            expected = [i, int(f"{i:0{a}b}"[::-1], 2), *coefficient(n, i % (n // 2))]
            require(line == "U " + " ".join(map(str, expected)), f"coefficient/permutation unit N={n} i={i}: {line} != {expected}")
        evidence.metrics.append({"check": "coefficient_bitrev_units", "n": n, "coefficients": n // 2,
                                 "permutations": n, "mismatches": 0})
    rng = random.Random(SEED)
    tuples = [((-32767, -32767), (-32767, -32767), (23170, -23170))]
    for a in ((-32768, -32768), (32767, 32767), (0, 0), (-1, 1), (32767, -32768)):
        for b in ((-32768, 32767), (32767, -32768), (1, -1)):
            for w in ((32767, 0), (0, -32768), (23170, -23170), (-32768, -32768)):
                tuples.append((a, b, w))
    for _ in range(1000):
        tuples.append(tuple(tuple(rng.randint(-32768, 32767) for _ in range(2)) for _ in range(3)))
    folder = evidence.folder / "butterfly-unit"
    folder.mkdir()
    (folder / "vectors.txt").write_text("".join(" ".join(str(c) for pair in vector for c in pair) + "\n" for vector in tuples))
    text = """
module tb;
reg signed [15:0] a_re,a_im,b_re,b_im,w_re,w_im;
wire signed [15:0] y0_re,y0_im,y1_re,y1_im;
wire [2:0] sat_inc;
billet_t1_butterfly b(.*);
integer fd,rc,i=0;
initial begin
 fd=$fopen("vectors.txt","r");
 if (!fd) $fatal(1,"missing unit vectors");
 while (!$feof(fd)) begin
  rc=$fscanf(fd,"%d %d %d %d %d %d\\n",a_re,a_im,b_re,b_im,w_re,w_im);
  if(rc!=6) $fatal(1,"malformed unit vector");
  #1; $display("B %0d %0d %0d %0d %0d %0d",i,$signed(y0_re),$signed(y0_im),$signed(y1_re),$signed(y1_im),sat_inc);
  i=i+1;
 end
 $finish;
end
endmodule
"""
    output = compile_sim(evidence, folder, text)
    require(len(output.splitlines()) == len(tuples), "butterfly unit missing data")
    total_clips = 0
    for i, (line, vector) in enumerate(zip(output.splitlines(), tuples)):
        u, v, clips = butterfly(*vector)
        require(line == "B " + " ".join(map(str, (i, *u, *v, clips))),
                f"butterfly unit mismatch vector={vector}: {line}")
        total_clips += clips
    require(total_clips > 0 and butterfly(*tuples[0])[0][0] == -32768, "unit clamp sensitivity")
    evidence.metrics.append({"check": "butterfly_unit", "vectors": len(tuples), "clamp_events": total_clips, "mismatches": 0})
    evidence.save()


def invalid_parameters(evidence):
    for n, override in [(n, None) for n in (-4, 0, 1, 3, 15, 257, 512)] + [(16, 3)]:
        suffix = f"-LOG2-{override}" if override is not None else ""
        parameters = f".N_POINTS({n})" + (f",.LOG2_N({override})" if override is not None else "")
        folder = evidence.folder / f"invalid-N{n}{suffix}"
        folder.mkdir()
        text = f"""
module tb;
wire in_ready,out_valid,out_last,frame_done,overflow_flag;
wire signed [15:0] out_re,out_im;
wire [31:0] saturation_count;
billet_t1_top #({parameters}) dut(.clk(1'b0),.rst_n(1'b0),.in_valid(1'b0),
.in_last(1'b0),.out_ready(1'b0),.in_re(16'sd0),.in_im(16'sd0),
.in_ready(in_ready),.out_valid(out_valid),.out_last(out_last),.frame_done(frame_done),
.overflow_flag(overflow_flag),.out_re(out_re),.out_im(out_im),.saturation_count(saturation_count));
initial begin #10; $fatal(1,"diagnostic was missing"); end
endmodule
"""
        bench = folder / "bridge.sv"
        bench.write_text(text)
        evidence.execute(["iverilog", "-g2012", "-Wall", "-s", "tb", "-o", folder / "sim.vvp",
                          *[ROOT / "rtl" / x for x in RTL_NAMES], bench], folder, "compile")
        code, output, stderr = evidence.execute(["vvp", folder / "sim.vvp"], folder, "simulate", expected_success=False)
        require(code != 0 and "PARAMETER ERROR: billet_t1_top" in output + stderr,
                f"invalid N={n} not rejected by explicit diagnostic")
        evidence.metrics.append({"check": "invalid_parameter", "n": n, "log2_override": override,
                                 "explicit_diagnostic": True, "simulator_exit": code})


def mutations(evidence, only=None):
    patches = {
        "twiddle_sign": ("billet_t1_twiddle_rom.sv", "assign w_im = value[15:0];", "assign w_im = -$signed(value[15:0]);"),
        "bit_reversal": ("billet_t1_bitrev.sv", "assign rev_idx[b] = idx[LOG2_N-1-b];", "assign rev_idx[b] = idx[b];"),
        "stage_scaling": ("billet_t1_butterfly.sv", "u_re = (a_re_ext + t_re_ext) >>> 1;", "u_re = (a_re_ext + t_re_ext) >>> 0;"),
        "butterfly_cross_term": ("billet_t1_butterfly.sv",
                                 "$signed({ri[PRODUCT_WIDTH-1], ri}) + $signed({ir[PRODUCT_WIDTH-1], ir});",
                                 "$signed({ri[PRODUCT_WIDTH-1], ri}) - $signed({ir[PRODUCT_WIDTH-1], ir});"),
    }
    # Existing asymmetric rail-safe scenario, with unchanged input and oracle.
    case = next(c for c in frames(16) if c["name"] == "mutation_discriminator")
    # A small complete smoke retaining directed resets is sufficient to discriminate.
    for name, (filename, before, after) in patches.items():
        if only is not None and name != only:
            continue
        folder = evidence.folder / name
        source_dir = folder / "rtl"
        source_dir.mkdir(parents=True)
        for source in RTL_NAMES:
            shutil.copyfile(ROOT / "rtl" / source, source_dir / source)
        target = source_dir / filename
        original = target.read_text()
        require(original.count(before) == 1, f"mutation anchor not unique: {name}")
        target.write_text(original.replace(before, after))
        record = {"check": "mutation", "name": name, "file": filename, "before": before, "after": after,
                  "source_hashes": {p.name: digest(p) for p in source_dir.glob("*.sv")},
                  "scenario": case["name"], "n": 16}
        # Each mutant must first compile and simulate successfully. Only actual
        # numeric rejection (not telemetry/protocol/tool failure) counts.
        try:
            behavior_cell(evidence, 16, [case] * 4, [source_dir / x for x in RTL_NAMES],
                          tag=name + "-behavior", require_coverage=False)
        except NumericalMismatch as exc:
            record.update(detected=True, rejection_kind="numerical_assertion", discriminating_failure=str(exc))
        else:
            raise VerificationFailure(f"undetected mutation: {name}")
        evidence.metrics.append(record)
        evidence.save()


def reachable_modules(netlist, top):
    modules = netlist["modules"]
    seen = set()

    def visit(name):
        require(name in modules, f"unresolved synthesized module {name}")
        if name in seen:
            return
        seen.add(name)
        for cell in modules[name].get("cells", {}).values():
            kind = cell["type"]
            if kind in modules:
                visit(kind)
            else:
                require(kind.startswith("$") and not kind.startswith("$paramod"),
                        f"black box or unresolved cell {kind}")
    visit(top)
    return {name: modules[name] for name in seen}


def inspect_synthesis(path, n, lowered=False):
    data = json.loads(path.read_text())
    modules = reachable_modules(data, "billet_t1_top")
    kinds = {}
    names = []
    internal_dont_care_bits = 0
    for name, module in modules.items():
        attributes = module.get("attributes", {})
        require(not int(attributes.get("blackbox", "0"), 2), "black-box module")
        # Yosys hdlname can have an escaped leading backslash.
        names.append(str(attributes.get("hdlname", name)).split(" ")[0].lstrip("\\"))
        for cell in module.get("cells", {}).values():
            kind = cell["type"]
            kinds[kind] = kinds.get(kind, 0) + 1
            require("latch" not in kind.lower(), f"inferred latch: {kind}")
            for connection in cell.get("connections", {}).values():
                require("z" not in connection, f"tristate synthesis connection in {kind}")
                # Disabled write data / unreachable ROM branches can retain
                # don't-cares; check -assert rejects genuinely undriven nets.
                internal_dont_care_bits += connection.count("x")
    top = data["modules"]["billet_t1_top"]
    for port in ("in_ready", "out_valid", "out_re", "out_im", "out_bin_idx", "frame_done", "saturation_count", "overflow_flag"):
        require(any(isinstance(bit, int) for bit in top["ports"][port]["bits"]), f"constant/disconnected top output {port}")
    require(any("dff" in kind.lower() for kind in kinds), "missing connected sequential state")
    if lowered:
        require(kinds.get("$mul", 0) >= 4, f"missing exact butterfly multipliers: {kinds}")
        for module_name in ("billet_t1_butterfly", "billet_t1_buffer_sched", "billet_t1_bitrev", "billet_t1_twiddle_rom"):
            require(module_name in names, f"missing real hierarchy {module_name}; {names}")
        memories = [cell for module in modules.values() for cell in module.get("cells", {}).values()
                    if cell["type"] in ("$mem_v2", "$mem")]
        capacity = sum(int(c["parameters"]["WIDTH"], 2) * int(c["parameters"]["SIZE"], 2) for c in memories)
        require(capacity >= 2 * n * 32 and len(memories) >= 2, f"omitted sample banks capacity={capacity}")
        for bank in ("g_legal.bank0", "g_legal.bank1"):
            require(bank in top["cells"], f"missing named sample bank {bank}")
            cell = top["cells"][bank]
            require(cell["type"] == "$mem_v2", f"sample bank is not memory: {bank}")
            parameters = {key: int(value, 2) for key, value in cell["parameters"].items()
                          if key in ("SIZE", "WIDTH", "RD_PORTS", "WR_PORTS")}
            require(parameters == {"SIZE": n, "WIDTH": 32, "RD_PORTS": 2, "WR_PORTS": 2},
                    f"wrong sample-bank capacity/port structure {bank}: {parameters}")
    else:
        require(sum(kinds.values()) > 100, "empty/trivial synthesized datapath")
    return {"cells": kinds, "reachable_modules": len(modules), "zero_latches": True,
            "internal_dont_care_bits": internal_dont_care_bits}


def synthesis(evidence, sizes=SIZES):
    for n in sizes:
        folder = evidence.folder / f"synthesis-N{n}"
        folder.mkdir()
        sources = " ".join(str(ROOT / "rtl" / x) for x in RTL_NAMES)
        script = f"""read_verilog -sv {sources}
chparam -set N_POINTS {n} billet_t1_top
hierarchy -check -top billet_t1_top
proc
opt
memory_collect
check -assert
write_json {folder / 'lowered.json'}
synth -top billet_t1_top -noabc
check -assert
write_json {folder / 'synthesized.json'}
stat
"""
        script_path = folder / "synth.ys"
        script_path.write_text(script)
        evidence.execute(["yosys", "-Q", "-T", "-s", script_path], folder, "yosys")
        lowered = inspect_synthesis(folder / "lowered.json", n, lowered=True)
        final = inspect_synthesis(folder / "synthesized.json", n)
        evidence.metrics.append({"check": "synthesis", "n": n, "lowered": lowered, "synthesized": final})
        evidence.save()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", choices=("behavior", "mutations", "synthesis"))
    parser.add_argument("--probe", choices=("smoke16", "synth2", "harness", "mutation_scaling"),
                        help="bounded preparation only; never substitutes for default acceptance")
    parser.add_argument("--repair-of", help="project-relative failed preparation receipt")
    args = parser.parse_args()
    evidence = Evidence(args.probe or args.check or "all", bool(args.probe), args.repair_of)
    try:
        tools = ("python3", "yosys") if args.check == "synthesis" or args.probe == "synth2" else (
            ("python3", "iverilog", "vvp") if args.check in ("behavior", "mutations") or args.probe else
            ("python3", "iverilog", "vvp", "yosys"))
        evidence.tools(tools)
        if args.probe == "smoke16":
            behavior_cell(evidence, 16)
        elif args.probe == "synth2":
            synthesis(evidence, (2,))
        elif args.probe == "harness":
            oracle_preflight(evidence)
            units(evidence)
            invalid_parameters(evidence)
            behavior_cell(evidence, 2)
        elif args.probe == "mutation_scaling":
            mutations(evidence, only="stage_scaling")
        else:
            if args.check in (None, "behavior"):
                units(evidence)
                invalid_parameters(evidence)
                for n in SIZES:
                    behavior_cell(evidence, n)
            if args.check in (None, "mutations"):
                mutations(evidence)
            if args.check in (None, "synthesis"):
                synthesis(evidence)
        evidence.finish()
        summary = f"PASS {args.probe or args.check or 'all'}: {evidence.folder.relative_to(ROOT) / 'receipt.json'}"
        (evidence.folder / "stdout.log").write_text(summary + "\n")
        print(summary)
        return 0
    except Exception as exc:
        diagnostic = traceback.format_exc()
        (evidence.folder / "stderr.log").write_text(diagnostic)
        evidence.finish(f"{type(exc).__name__}: {exc}")
        print(f"FAIL: {exc}; receipt={evidence.folder.relative_to(ROOT) / 'receipt.json'}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
