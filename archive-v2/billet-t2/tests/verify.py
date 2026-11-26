#!/usr/bin/env python3
"""Public-pin verification; all child commands have retained, bounded receipts."""
import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import random
import shutil
import subprocess
import sys
import time
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parent))
from oracle import TWIDDLES, dft, spectral_error, transform

ROOT = Path(__file__).resolve().parents[1]
TIMEOUT = 3600


def now():
    return datetime.now(timezone.utc).isoformat()


def dump(path, data):
    path.write_text(json.dumps(data, indent=2) + "\n")


def source_hashes():
    return {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
            for pattern in ("rtl/*.sv", "tests/*", "design/*.md",
                            "billet_t1_reference/rtl/*.sv")
            for p in sorted(ROOT.glob(pattern)) if p.is_file()}


class Execution:
    def __init__(self, out):
        try:
            out.mkdir(parents=True, exist_ok=False)
        except FileExistsError:
            if not out.is_dir():
                raise
            out = out / ("run-" + uuid.uuid4().hex)
            out.mkdir(exist_ok=False)
        self.out = out
        self.commands = []
        self.sources = source_hashes()
        self.started = now()
        self.versions = {}

    def run(self, name, argv, expected_failure=False):
        stdout = self.out / (name + ".stdout.log")
        stderr = self.out / (name + ".stderr.log")
        receipt = {"argv": [str(x) for x in argv], "cwd": str(ROOT),
                   "started_at": now(), "timeout_s": TIMEOUT,
                   "stdout": str(stdout.relative_to(ROOT)),
                   "stderr": str(stderr.relative_to(ROOT)),
                   "source_sha256": self.sources, "tool_versions": self.versions,
                   "expected_checker_rejection": expected_failure}
        start = time.monotonic()
        try:
            with stdout.open("w") as so, stderr.open("w") as se:
                result = subprocess.run(argv, cwd=ROOT, stdout=so, stderr=se,
                                        timeout=TIMEOUT, check=False)
            receipt.update(exit_code=result.returncode, timed_out=False)
        except subprocess.TimeoutExpired:
            receipt.update(exit_code=None, timed_out=True)
            raise
        finally:
            receipt.update(ended_at=now(), duration_s=time.monotonic() - start)
            path = self.out / (name + ".receipt.json")
            dump(path, receipt)
            self.commands.append(str(path.relative_to(ROOT)))
        if expected_failure:
            assert result.returncode != 0, "deliberate defect escaped comparison"
            assert "MISMATCH" in stdout.read_text(), "not a scoreboard rejection"
        elif result.returncode != 0:
            raise RuntimeError(f"{name} exit {result.returncode}: {stdout}, {stderr}")
        return stdout.read_text() + (stderr.read_text() if name.startswith("version-") else "")

    def inventory(self, tools):
        self.versions["python3"] = sys.version
        for tool in tools:
            if shutil.which(tool) is None:
                raise RuntimeError(f"required tool unavailable: {tool}")
            flag = "-V" if tool in ("iverilog", "vvp", "yosys") else "--version"
            self.versions[tool] = self.run("version-" + tool, [tool, flag]).strip()

    def finish(self, status, **details):
        dump(self.out / "result.json",
             {"status": status, "started_at": self.started, "ended_at": now(),
              "source_sha256": self.sources, "tool_versions": self.versions,
              "receipts": self.commands, **details})
        assert self.sources == source_hashes(), "verification inputs changed during execution"


class Vectors:
    """Schedule-derived external expectations, not a DUT-state scoreboard."""
    def __init__(self, path, reference=False):
        self.file = path.open("w")
        self.reference = reference
        self.row = 0
        self.count = 0
        self.cfg = (8 if reference else 4, 0, 0, 0)
        self.frames = []
        self.coverage = Counter()
        self.reset()

    def emit(self, expected, *, reset=1, valid=0, last=0, ready=1,
             sample=(0, 0), cfg=None):
        if cfg is not None:
            self.cfg = cfg
        inputs = (reset, valid, last, ready, *sample, *self.cfg)
        values = [*expected, 0]
        assert len(inputs) == 10 and len(values) == 12
        self.file.write(" ".join(map(str, inputs)) + " " +
                        " ".join(f"{x & 0xffffffff:x}" for x in values) + "\n")
        self.row += 1

    def expected(self, *, loading=False, busy=True, payload=None, done=0):
        legal = 4 <= self.cfg[0] <= 8 and self.cfg[2] != 3
        in_ready = int(loading and (busy or legal or self.reference))
        error = int(loading and not busy and not legal and not self.reference)
        if payload is None:
            valid, last, re_, im, index, exp = (0,) * 6
        else:
            re_, im, index, exp, last = payload
            valid = 1
        return [in_ready, valid, last, done, int(self.count != 0), error,
                re_, im, index, exp, self.count]

    def reset(self):
        self.count = 0
        self.emit([0] * 11, reset=0)
        self.emit([0] * 11, reset=0)
        self.idle()
        self.coverage["reset_epochs"] += 1

    def idle(self, cfg=None, valid=0, done=0):
        if cfg is not None:
            self.cfg = cfg
        self.emit(self.expected(loading=True, busy=False, done=done), valid=valid)
        if valid and (self.cfg[0] not in range(4, 9) or self.cfg[2] == 3):
            self.coverage["invalid_config_rejections"] += 1

    def frame(self, samples, inverse, mode, mask, name, stalls=True,
              abort=None, change_cfg=True):
        n = len(samples)
        logn = n.bit_length() - 1
        output, exponent, stages = transform(samples, inverse, mode, mask)
        cfg = (logn, inverse, mode, mask)
        start_count = self.count
        first_row = self.row
        for j, x in enumerate(samples):
            self.cfg = cfg if j == 0 or not change_cfg else (15, 1-inverse, 3, 255-mask)
            if stalls and j % 11 == 3:
                self.emit(self.expected(loading=True), valid=0, sample=x)
            self.emit(self.expected(loading=j != n-1), valid=1,
                      last=int(j % 7 == 0), sample=x)
            if abort == "load" and j == 2:
                self.reset()
                self.coverage["reset/load"] += 1
                return
        load_end = self.row - 1
        for s, stage in enumerate(stages):
            if self.reference:
                # T1 clamps both butterfly results together, rather than
                # normalization entry order. Diagnostics are compared at outputs.
                for c in range(n):
                    self.emit(self.expected())
            else:
                for c in range(n):
                    if abort in ("butterfly_read", "butterfly_write") and s == 0:
                        if c == (0 if abort == "butterfly_read" else 1):
                            self.reset()
                            self.coverage["reset/"+abort] += 1
                            return
                    if change_cfg:
                        self.cfg = ((4, 1, 2, 255) if c % 2 else (15, 0, 3, 0))
                    self.emit(self.expected(), valid=int(c % 13 == 0))
                for j, inc in enumerate(stage["increments"]):
                    if abort == "normalize_read" and s == 0 and j == 1:
                        self.reset()
                        self.coverage["reset/"+abort] += 1
                        return
                    self.emit(self.expected())
                    if abort == "normalize_write" and s == 0 and j == 0:
                        self.reset()
                        self.coverage["reset/"+abort] += 1
                        return
                    self.count = min(0xffffffff, self.count + inc)
                    self.emit(self.expected())
        if self.reference:
            self.count = min(0xffffffff, start_count +
                             sum(sum(s["increments"]) for s in stages))
        assert self.row - 1 - load_end == (n if self.reference else 3*n)*logn
        if abort == "fetch":
            self.reset()
            self.coverage["reset/fetch"] += 1
            return
        accepts = []
        for j, (re_, im) in enumerate(output):
            payload = (re_, im, j, exponent, int(j == n-1))
            self.emit(self.expected(payload=payload))
            if j == 0:
                assert self.row - 1 - load_end == (n if self.reference else 3*n)*logn + 1
            stall_count = (37 if j in (0, n-1) else 3 if j % 9 == 0 else 0) if stalls else 0
            for _ in range(stall_count):
                if change_cfg:
                    self.cfg = ((8, 1, 0, 255) if self.cfg[0] == 15 else (15, 0, 3, 0))
                self.emit(self.expected(payload=payload), ready=0, valid=1)
            if abort == "send" and j == 0:
                self.reset()
                self.coverage["reset/send"] += 1
                return
            accepts.append(self.row)
            self.emit(self.expected(loading=j == n-1, busy=False,
                                    done=int(j == n-1)), valid=1)
        if not stalls:
            assert accepts[-1] - load_end == (n if self.reference else 3*n)*logn + 2*n
        self.coverage["frames"] += 1
        self.coverage[f"N{n}/I{inverse}/M{mode}"] += 1
        self.coverage["saturations"] += self.count - start_count
        for stage in stages:
            self.coverage["shift" if stage["shift"] else "no_shift"] += 1
            if mode == 2:
                self.coverage["bfp_shift" if stage["shift"] else "bfp_no_shift"] += 1
                self.coverage["bfp_last_only"] += int(stage["last_only"])
                self.coverage["bfp_residual_saturation"] += sum(stage["increments"])
        self.frames.append({"name": name, "n": n, "inverse": inverse,
                            "mode": mode, "mask": mask, "input": samples,
                            "expected": output, "exponent": exponent,
                            "saturation_increment": self.count-start_count,
                            "start_row": first_row, "accept_rows": accepts,
                            "stages": stages})
        self.idle()

    def close(self):
        self.file.close()
        return self.frames


def compile_bridge(ex, reference=False):
    name = "t1" if reference else "t2"
    binary = ex.out / (name + ".vvp")
    if reference:
        directory = ROOT / "billet_t1_reference/rtl"
        sources = [directory / "billet_t1_pkg.sv"] + [
            p for p in sorted(directory.glob("*.sv")) if p.name != "billet_t1_pkg.sv"]
    else:
        sources = sorted((ROOT / "rtl").glob("*.sv"))
    ex.run("compile-" + name, ["iverilog", "-g2012", "-Wall", "-s", "bridge",
           *(["-DREFERENCE"] if reference else []), "-o", str(binary),
           str(ROOT / "tests/bridge.sv"), *map(str, sources)])
    return binary


def simulate(ex, binary, vector_path, label):
    trace_path = ex.out / (label + ".trace")
    log = ex.run(label, ["vvp", str(binary), "+vectors=" + str(vector_path),
                        "+trace=" + str(trace_path)])
    lines = trace_path.read_text().splitlines()
    assert lines and lines[-1].startswith("COMPLETE "), "missing completion sentinel"
    cycles = int(lines[-1].split()[1])
    assert f"COMPARED {cycles} cycles" in log and cycles > 0
    with vector_path.open() as vectors:
        assert cycles == sum(1 for _ in vectors), "incomplete vector execution"
    parsed = [[int(x) for x in line.split()] for line in lines[:-1]]
    assert len({row[0] for row in parsed}) == len(parsed), "duplicate trace cycle"
    return {row[0]: row[1:] for row in parsed}


def bind_actual(frames, trace, receipt):
    expected_rows = {row for frame in frames for row in frame["accept_rows"]}
    assert set(trace) == expected_rows, "lost, duplicated, or abandoned output"
    for frame in frames:
        actual = [trace[row] for row in frame["accept_rows"]]
        assert [a[:2] for a in actual] == [list(x) for x in frame["expected"]]
        assert [a[2] for a in actual] == list(range(frame["n"]))
        assert all(a[4] == frame["exponent"] for a in actual)
        frame["actual"] = [a[:2] for a in actual]
        frame["actual_final_count"] = actual[-1][5]
        frame["outcome"] = "passed"
        frame["raw_receipt"] = receipt


def patterns(n):
    rng = random.Random(4200+n)
    return {
        "zero": [(0, 0)]*n,
        "impulse+": [(64, 0)]+[(0, 0)]*(n-1),
        "impulse-": [(-32768, 1)]+[(0, 0)]*(n-1),
        "dc": [(2000, -3000)]*n,
        "alternating": [(32767 if j % 2 else -32768, 0) for j in range(n)],
        "tone": [(round(900*math.cos(6*math.pi*j/n)),
                  round(900*math.sin(6*math.pi*j/n))) for j in range(n)],
        "corner-tone": [(32767 if math.cos(6*math.pi*j/n+0.123) > 0 else -32768,
                         32767 if math.sin(6*math.pi*j/n+0.123) > 0 else -32768)
                        for j in range(n)],
        "extrema": [(rng.choice((-32768, 32767)),
                     rng.choice((-32768, 32767))) for _ in range(n)],
        "last-trigger": [(0, 0)]*(n//2-1)+[(32767, 0)]+
                        [(0, 0)]*(n//2-1)+[(32767, 0)],
    }


def make_matrix(v, smoke=False):
    for logn in ((4,) if smoke else range(4, 9)):
        n = 1 << logn
        for inverse in range(2):
            for mode in range(3):
                for name, samples in patterns(n).items():
                    v.frame(samples, inverse, mode, 0x55,
                            f"{n}/{inverse}/{mode}/{name}", stalls=True)
                for seed in (17, 89, 503):
                    rng = random.Random(seed + n*10 + inverse)
                    samples = [(rng.randint(-32768, 32767), rng.randint(-32768, 32767))
                               for _ in range(n)]
                    v.frame(samples, inverse, mode, 0xaa,
                            f"{n}/{inverse}/{mode}/random{seed}", stalls=False)
            masks = {0, 255, 0x55, 0xaa, (1 << logn)-1,
                     *[1 << s for s in range(logn)]}
            if logn < 8:
                masks.add(255 ^ ((1 << logn)-1))
            for mask in sorted(masks):
                rng = random.Random(360 + n + inverse)
                samples = [(rng.randint(-512, 512), rng.randint(-512, 512)) for _ in range(n)]
                v.frame(samples, inverse, 1, mask, f"mask/{n}/{inverse}/{mask}", stalls=False)
    if not smoke:
        # No reset between these transitions: both memory extremes and exponent resets.
        for n in (16, 256, 16):
            v.frame(patterns(n)["zero"], 0, 2, 0, f"transition/{n}", stalls=False)


def numerical(ex, binary):
    """Second simulation batch depends on actual first-pass RTL outputs."""
    v = Vectors(ex.out / "numerical-forward.vec")
    for logn in range(4, 9):
        n = 1 << logn
        for seed in (17, 89, 503):
            rng = random.Random(seed+n)
            samples = [(rng.randint(-64, 64), rng.randint(-64, 64)) for _ in range(n)]
            for mode in (0, 1, 2):
                v.frame(samples, 0, mode, 0, f"random/{n}/{seed}/{mode}", stalls=False)
        for mode in (0, 2):
            # A sample-zero impulse of 64 is exact in both modes for N<=64.
            # A delayed impulse exercises twiddle quantization at every length.
            impulse = [(0, 0), (64, 0)] + [(0, 0)]*(n-2)
            v.frame(impulse, 0, mode, 0,
                    f"impulse/{n}/{mode}", stalls=False)
        for inverse in (0, 1):
            tone = [(round(64*math.cos(6*math.pi*j/n)),
                     round(64*math.sin(6*math.pi*j/n))) for j in range(n)]
            v.frame(tone, inverse, 1, 0,
                    f"orientation/{n}/{inverse}", stalls=False)
    frames = v.close()
    bind_actual(frames, simulate(ex, binary, ex.out / "numerical-forward.vec", "numerical-forward"),
                str((ex.out/"numerical-forward.receipt.json").relative_to(ROOT)))
    inv = Vectors(ex.out / "reconstruction.vec")
    selected = [f for f in frames if f["name"].startswith("random/") and f["mode"] == 1]
    for f in selected:
        assert f["saturation_increment"] == 0
        inv.frame(f["actual"], 1, 0, 0, f["name"], stalls=False)
    reconstructed = inv.close()
    bind_actual(reconstructed, simulate(ex, binary, ex.out / "reconstruction.vec", "reconstruction"),
                str((ex.out/"reconstruction.receipt.json").relative_to(ROOT)))
    measurements = []
    for forward, backward in zip(selected, reconstructed):
        errors = [tuple(a-b for a, b in zip(actual, original))
                  for actual, original in zip(backward["actual"], forward["input"])]
        maximum = max(abs(e) for pair in errors for e in pair)
        rms = math.sqrt(sum(a*a+b*b for a, b in errors)/forward["n"])
        assert backward["saturation_increment"] == 0
        assert maximum <= 32 and rms <= 8, (forward["name"], maximum, rms)
        mathematical = dft(forward["input"])
        # Integer truncation is stage dependent; triangle bound 4*N input LSB
        # is deliberately conservative, but opposite direction fails tone checks below.
        forward_error = max(abs(complex(*x)-y) for x, y in zip(forward["actual"], mathematical))
        assert forward_error <= 4*forward["n"]
        measurements.append({"case": forward["name"], "max_component_error_lsb": maximum,
                             "complex_rms_error_lsb": rms, "limits": [32, 8],
                             "direct_dft_max_error_lsb": forward_error})
    for f in frames:
        if f["name"].startswith("orientation/"):
            mathematical = dft(f["input"], bool(f["inverse"]))
            peak = max(range(f["n"]), key=lambda k: abs(complex(*f["actual"][k])))
            direct_error = max(abs(complex(*x)-y) for x, y in zip(f["actual"], mathematical))
            assert f["saturation_increment"] == 0, f"{f['name']}: orientation stimulus saturated"
            assert peak == (f["n"]-3 if f["inverse"] else 3), (f["name"], peak)
            assert direct_error <= 4*f["n"], (f["name"], direct_error, 4*f["n"])
            measurements.append({"case": f["name"], "peak": peak,
                                 "tone_amplitude_lsb": 64,
                                 "saturation_increment": f["saturation_increment"],
                                 "direct_dft_max_error_lsb": direct_error,
                                 "direct_dft_error_limit_lsb": 4*f["n"],
                                 "direct_error_sse": spectral_error(f["actual"], 0, mathematical)})
    for n in (16, 32, 64, 128, 256):
        fixed = next(f for f in frames if f["name"] == f"impulse/{n}/0")
        bfp = next(f for f in frames if f["name"] == f"impulse/{n}/2")
        assert fixed["exponent"] == n.bit_length()-1 and bfp["exponent"] == 0
        mathematical = dft(fixed["input"])
        ef = spectral_error(fixed["actual"], fixed["exponent"], mathematical)
        eb = spectral_error(bfp["actual"], bfp["exponent"], mathematical)
        assert eb < ef, f"impulse/{n}: BFP SSE {eb} must be strictly below fixed SSE {ef}"
        assert fixed["saturation_increment"] == bfp["saturation_increment"] == 0
        measurements.append({"case": f"impulse-improvement/{n}", "impulse_sample_index": 1,
                             "amplitude_lsb": 64, "fixed_exponent": fixed["exponent"],
                             "bfp_exponent": bfp["exponent"],
                             "fixed_sse": ef, "bfp_sse": eb})
        for seed in (17, 89, 503):
            cases = [next(f for f in frames if f["name"] == f"random/{n}/{seed}/{mode}")
                     for mode in (0, 2)]
            mathematical = dft(cases[0]["input"])
            measurements.append({"case": f"seeded-comparison/{n}/{seed}",
                "fixed_sse": spectral_error(cases[0]["actual"], cases[0]["exponent"], mathematical),
                "bfp_sse": spectral_error(cases[1]["actual"], cases[1]["exponent"], mathematical)})
    for measurement in measurements:
        measurement["outcome"] = "passed"
        measurement["raw_receipts"] = [
            str((ex.out/(name+".receipt.json")).relative_to(ROOT))
            for name in ("numerical-forward", "reconstruction")]
    dump(ex.out / "numerical-measurements.json", measurements)
    dump(ex.out / "numerical-frames.json", frames + reconstructed)
    return measurements


def compatibility(ex, t2):
    ref = compile_bridge(ex, reference=True)
    all_frames = []
    for reference in (False, True):
        label = "compat-t1" if reference else "compat-t2"
        v = Vectors(ex.out / (label + ".vec"), reference)
        for name, samples in patterns(256).items():
            v.frame(samples, 0, 0, 255, name, stalls=False, change_cfg=False)
        for seed in (17, 89, 503):
            rng = random.Random(seed)
            samples = [(rng.randint(-32768,32767), rng.randint(-32768,32767)) for _ in range(256)]
            v.frame(samples, 0, 0, 0, f"random{seed}", stalls=False, change_cfg=False)
        frames = v.close()
        trace = simulate(ex, ref if reference else t2, ex.out / (label + ".vec"), label)
        bind_actual(frames, trace, str((ex.out/(label+".receipt.json")).relative_to(ROOT)))
        all_frames.append(frames)
    for f2, f1 in zip(*all_frames):
        assert f2["actual"] == f1["actual"]
        assert f2["actual_final_count"] == f1["actual_final_count"]
    dump(ex.out / "compatibility.json", {
        "frames": all_frames, "components_compared": sum(f["n"]*2 for f in all_frames[0])})


def behavior(ex, smoke=False):
    ex.inventory(("iverilog", "vvp"))
    unit_checks(ex)
    binary = compile_bridge(ex)
    v = Vectors(ex.out / "behavior.vec")
    for length in (0, 3, 9, 15):
        for mode in range(4):
            v.idle((length, 0, mode, 0), valid=1)
    for length in range(4, 9):
        v.idle((length, 0, 3, 0), valid=1)
    v.idle((4, 0, 0, 0))
    for phase in ("load", "butterfly_read", "butterfly_write",
                  "normalize_read", "normalize_write", "fetch", "send"):
        v.frame(patterns(16)["extrema"], 0, 1, 0, "abort/"+phase, abort=phase)
    make_matrix(v, smoke)
    frames = v.close()
    trace = simulate(ex, binary, ex.out / "behavior.vec", "behavior")
    bind_actual(frames, trace, str((ex.out/"behavior.receipt.json").relative_to(ROOT)))
    assert v.coverage["shift"] > 0 and v.coverage["no_shift"] > 0
    assert v.coverage["bfp_last_only"] > 0 and v.coverage["saturations"] > 0
    assert v.coverage["bfp_shift"] > 0 and v.coverage["bfp_no_shift"] > 0
    assert v.coverage["bfp_residual_saturation"] > 0
    assert v.coverage["invalid_config_rejections"] == 21
    for phase in ("load", "butterfly_read", "butterfly_write", "normalize_read",
                  "normalize_write", "fetch", "send"):
        assert v.coverage["reset/"+phase] == 1
    for n in ((16,) if smoke else (16, 32, 64, 128, 256)):
        for inverse in range(2):
            for mode in range(3):
                assert v.coverage[f"N{n}/I{inverse}/M{mode}"] >= 12
    dump(ex.out / "frames.json", frames)
    dump(ex.out / "coverage.json", dict(v.coverage))
    sensitivity(ex, binary)
    if not smoke:
        numerical(ex, binary)
        compatibility(ex, binary)
    return {"cycles": v.row, "frames": len(frames), "coverage": dict(v.coverage),
            "scope": "bounded preparation" if smoke else "full admitted behavior",
            "limitations": ["No formal proof or physical sign-off.",
                           "32-bit cumulative saturation rollover requires over 2^32 clamped components; not reached by simulation."]}


def sensitivity(ex, binary):
    for defect in ("sample", "latency", "bit-order", "ready"):
        path = ex.out / ("negative-" + defect + ".vec")
        v = Vectors(path)
        v.frame([(64, 7)] + [(0, 0)]*15, 0, 1, 0, "private-fixture", stalls=False)
        v.close()
        lines = path.read_text().splitlines()
        # Alter a private expected observation, never accepted RTL.
        at = next(i for i, line in enumerate(lines)
                  if line.split()[11] == "1" and
                  (defect != "bit-order" or line.split()[18] == "1"))
        fields = lines[at].split()
        pin = {"sample": 6, "latency": 1, "bit-order": 8, "ready": 0}[defect]
        fields[10+pin] = "8" if defect == "bit-order" else f"{int(fields[10+pin],16)^1:x}"
        lines[at] = " ".join(fields)
        path.write_text("\n".join(lines)+"\n")
        ex.run("negative-" + defect, ["vvp", str(binary), "+vectors="+str(path),
               "+trace="+str(ex.out / ("negative-"+defect+".trace"))], expected_failure=True)


def unit_checks(ex):
    # Independently generated table is checked by simulation against BOTH ROMs.
    body = []
    for k, (wr, wi) in enumerate(TWIDDLES):
        body.append(f"k={k}; inv=0; #1; "
                    f"if ($signed(wr)!=={wr} || $signed(wi)!=={wi} || "
                    f"$signed(rwr)!=={wr} || $signed(rwi)!=={wi}) "
                    f"$fatal(1,\"ROM {k} wr=%0d wi=%0d reference_wr=%0d reference_wi=%0d\",wr,wi,rwr,rwi); "
                    f"inv=1; #1; if ($signed(wr)!=={wr} || $signed(wi)!=={-wi}) $fatal(1,\"CONJ {k}\");")
    for logn in range(4, 9):
        for idx in range(1 << logn):
            rev = int(f"{idx:0{logn}b}"[::-1], 2)
            body.append(f"idx={idx}; logn={logn}; #1; if (rev!==8'd{rev}) $fatal(1,\"BITREV\");")
    rng = random.Random(1717)
    for i in range(800):
        a, b = [(rng.randint(-32768, 32767), rng.randint(-32768, 32767)) for _ in range(2)]
        wr, wi = TWIDDLES[i % 128]
        if i % 2:
            wi = -wi
        tr, ti = (b[0]*wr-b[1]*wi)//32768, (b[0]*wi+b[1]*wr)//32768
        expected = [a[0]+tr, a[1]+ti, a[0]-tr, a[1]-ti]
        body.append(f"ar={a[0]}; ai={a[1]}; br={b[0]}; bi={b[1]}; bwr={wr}; bwi={wi}; #1; " +
                    " ".join(f"if ($signed({p})!=={e}) $fatal(1,\"BUTTERFLY {i}\");"
                             for p, e in zip(("ur","ui","vr","vi"), expected)))
    # Range boundaries, negative odd flooring, final-observation contribution,
    # simultaneous stage commit/clear and exponent frame reset.
    for mode in range(3):
        for bit in range(2):
            for x in (-131072, -65537, -65536, -32769, -32768, -3, -1, 0, 32767, 32768, 65535, 131071):
                shift = int(mode == 0 or mode == 1 and bit or mode == 2 and not -32768 <= x <= 32767)
                value = x // (1 << shift)
                clip = max(-32768, min(32767, value))
                inc = int(value != clip)
                body.append(f"mode={mode}; bitshift={bit}; fs=1; tick; fs=0; "
                            f"r0={x}; obs=1; tick; obs=0; nr={x}; ni=0; #1; "
                            f"if (shift!==1'd{shift} || $signed(sr)!=={clip} || si!==0 || inc!==2'd{inc}) "
                            "$fatal(1,\"SCALER_BOUNDARY\"); "
                            f"commit=1; ss=1; tick; commit=0; ss=0; #1; "
                            f"if (exp!==4'd{shift}) $fatal(1,\"COMMIT\"); "
                            "mode=2; #1; if (shift!==0) $fatal(1,\"STAGE_CLEAR\"); "
                            "fs=1; tick; fs=0; #1; if (exp!==0) $fatal(1,\"FRAME_CLEAR\");")
    for lane in range(4):
        for x in (-65537, -32769, -32768, -1, 32767, 32768, 65536):
            shift = int(not -32768 <= x <= 32767)
            value = x // (1 << shift)
            clip = max(-32768, min(32767, value))
            inc = 2*int(value != clip)
            body.append(
                "mode=2; fs=1; tick; fs=0; r0=0; r1=0; r2=0; r3=0; "
                f"r{lane}={x}; obs=1; tick; obs=0; nr={x}; ni={x}; #1; "
                f"if (shift!==1'd{shift} || $signed(sr)!=={clip} || "
                f"$signed(si)!=={clip} || inc!==2'd{inc}) $fatal(1,\"OBSERVE_LANE_{lane}\");")
    text = """
`timescale 1ns/1ps
module units;
reg [7:0] k=255,idx=255; reg [3:0] logn=4; reg inv=0;
wire signed [16:0] wr,wi; wire signed [15:0] rwr,rwi; wire [7:0] rev;
billet_t2_twiddle_rom rom(k[6:0],inv,wr,wi);
billet_t1_twiddle_rom reference_rom(k,rwr,rwi);
billet_t2_bitrev reversal(idx,logn,rev);
reg signed [15:0] ar=0,ai=0,br=0,bi=0;
reg signed [16:0] bwr=0,bwi=0;
wire signed [17:0] ur,ui,vr,vi;
billet_t2_butterfly butterfly(ar,ai,br,bi,bwr,bwi,ur,ui,vr,vi);
reg clk=0,rst=0,fs=0,ss=0,obs=0,commit=0,bitshift=0;
reg [1:0] mode=0; reg signed [17:0] r0=0,r1=0,r2=0,r3=0,nr=0,ni=0;
wire signed [15:0] sr,si; wire [1:0] inc; wire [3:0] exp; wire shift;
billet_t2_bfp_scaler scaler(clk,rst,fs,ss,obs,commit,mode,bitshift,
                           r0,r1,r2,r3,nr,ni,sr,si,inc,exp,shift);
task tick; begin #2; clk=1; #1; clk=0; #1; end endtask
initial begin #1; rst=1;
""" + "\n".join(body) + '\n$display("UNITS_COMPLETE"); $finish; end\nendmodule\n'
    source = ex.out / "units.sv"
    source.write_text(text)
    binary = ex.out / "units.vvp"
    ex.run("compile-units", ["iverilog", "-g2012", "-Wall", "-s", "units", "-o", str(binary),
           str(source), *map(str, sorted((ROOT/"rtl").glob("*.sv"))),
           str(ROOT/"billet_t1_reference/rtl/billet_t1_twiddle_rom.sv")])
    assert "UNITS_COMPLETE" in ex.run("units", ["vvp", str(binary)])


def synthesis(ex):
    ex.inventory(("yosys",))
    script = ex.out / "synthesis.ys"
    netlist = ex.out / "netlist.json"
    script.write_text(
        "read_verilog -sv " + " ".join(str(p) for p in sorted((ROOT/"rtl").glob("*.sv"))) +
        "\nhierarchy -check -top billet_t2_top\n"
        "proc\nopt\ncheck -assert\n"
        "select -assert-none t:$dlatch t:$adlatch t:$dlatchsr\n"
        "memory -nomap\nopt\ncheck -assert\n"
        "select -assert-none t:$dlatch t:$adlatch t:$dlatchsr\n"
        "stat\nwrite_json " + str(netlist) + "\n")
    log = ex.run("yosys", ["yosys", "-T", "-s", str(script)])
    data = json.loads(netlist.read_text())
    modules = data["modules"]
    assert "billet_t2_top" in modules
    cells = Counter()
    sequential_bits = 0
    memory_bits = 0
    for name, module in modules.items():
        assert not int(module.get("attributes", {}).get("blackbox", "0"), 2), name
        for cell in module["cells"].values():
            typ = cell["type"]
            cells[typ] += 1
            assert "latch" not in typ.lower()
            assert typ.startswith("$") or typ in modules, f"unresolved {typ}"
            if "dff" in typ.lower():
                sequential_bits += len(cell["connections"]["Q"])
            if typ == "$mem_v2":
                memory_bits += int(cell["parameters"]["WIDTH"], 2)*int(cell["parameters"]["SIZE"], 2)
    assert sequential_bits >= 100, cells
    assert memory_bits >= 17408, (memory_bits, cells)
    assert cells["$mul"] >= 4 and cells["$add"] >= 4 and cells["$sub"] >= 2, cells
    assert "Found and reported 0 problems" in log
    result = {"frontend": "Yosys native read_verilog -sv (supported synthesizable subset)",
              "cell_types": dict(cells), "sequential_bits": sequential_bits,
              "memory_bits": memory_bits, "netlist": str(netlist.relative_to(ROOT)),
              "physical_signoff": False}
    dump(ex.out / "statistics.json", result)
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", choices=("behavior", "synthesis"), required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--preparation-smoke", action="store_true")
    args = parser.parse_args()
    out = args.output_dir.resolve()
    out.relative_to(ROOT)
    ex = Execution(out)
    try:
        details = behavior(ex, args.preparation_smoke) if args.check == "behavior" else synthesis(ex)
        ex.finish("passed", **details)
    except Exception as error:
        ex.finish("failed", error=repr(error))
        raise
    print(json.dumps({"status": "passed",
                      "result": str((ex.out/"result.json").relative_to(ROOT))}))


if __name__ == "__main__":
    main()
