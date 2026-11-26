#!/usr/bin/env python3
"""Run the admitted Billet-T1 L1 suites with retained simulator witnesses."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import sys
import tempfile

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent))
from oracle import SIZES, board_frames, dft_quality, fft, frame, pack, unpack


ROOT = Path(__file__).resolve().parents[1]
SHELL = ["fpga/longspeak/Types/ShellTypes.sv", "fpga/longspeak/longspeak_dma_cdc.sv",
         "fpga/longspeak/SoftShell.sv"]
VENDOR = ["altera_mf.v"]
FROZEN_IDS = {"zero", "complex_impulse", "negative_floor", "opposite_rails", "mixed_components"}


def require(ok, message):
    if not ok:
        raise ValueError(message)


def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def frozen_frames(path):
    asset = json.loads(path.read_text())
    require(asset.get("schema") == "vulcan-black-box-vectors/v1" and set(asset["cases"]) == FROZEN_IDS,
            "frozen oracle schema or case set differs from admission")

    def unpack_row(row, prefix):
        require(set(row) == {f"{prefix}{j}_{axis}" for j in range(2) for axis in ("re", "im")}
                and all(type(x) is int and 0 <= x < 65536 for x in row.values()),
                "frozen oracle must contain all unsigned 16-bit patterns")
        return [unpack(row[f"{prefix}{j}_re"] | (row[f"{prefix}{j}_im"] << 16)) for j in range(2)]

    result = []
    for name, row in sorted(asset["cases"].items()):
        x, y = unpack_row(row["inputs"], "x"), unpack_row(row["expected"], "y")
        require(fft(x) == (y, 0), f"independent integer model disagrees with frozen case {name}")
        result.append((name, x, y))
    return result


def write_vectors(path, cases):
    with path.open("w", encoding="ascii") as f:
        f.write(f"{len(cases)}\n")
        for kind, clamps, preload, samples, expected in cases:
            f.write(f"{kind} {clamps} {preload}\n")
            for x, y in zip(samples, expected, strict=True):
                f.write(f"{pack(x):08x} {pack(y):08x}\n")


def core_vectors(work, frozen):
    case_ids = {}
    for n in SIZES:
        cases = []
        names = []

        def append(name, x, kind=0, preload=0):
            y, clamps = fft(x)
            cases.append((kind, clamps, preload, x, y))
            names.append(name)

        if n == 2:
            for name, x, y in frozen:
                cases.append((2, 0, 0, x, y))
                names.append(name)
        append("rail_safe_tone", frame(n, "tone"), 1)
        append("off_center_impulse", frame(n, "impulse"))
        for seed in range(3):
            append(f"broadband_{seed}", frame(n, "broadband", 0xB111E7 + seed))
        append("clipping_rails", frame(n, "rails"))
        append("repeat_after_rails", [(0, 0)] * n)
        if n == 16:
            require(fft(frame(n, "rails"))[1] > 1, "rollover witness needs multiple real clamps")
            append("saturating_counter", frame(n, "rails"), 3, -2)
        case_ids[n] = names
        write_vectors(work / f"core{n}.txt", cases)
    return case_ids


def shell_vectors(work, frozen):
    names = {}
    for n in (2, 4, 8, 256):
        cases = [(2, 0, 0, x, y) for _, x, y in frozen] if n == 2 else []
        names[n] = [name for name, _, _ in frozen] if n == 2 else []
        stimulus = {"tone": frame(n, "tone"), "rails": frame(n, "rails")}
        stimulus.update(board_frames() if n == 256 else {"broadband": frame(n, "broadband", n)})
        for name, x in stimulus.items():
            y, clamps = fft(x)
            cases.append((0, clamps, 0, x, y))
            names[n].append(name)
        write_vectors(work / f"shell{n}.txt", cases)
    return names


class Runner:
    def __init__(self, work, retained):
        self.work = work
        self.retained = retained
        manifest = json.loads((ROOT / "rtl/longspeak_sources.json").read_text())
        require(manifest["schema"] == "vulcan-longspeak-sources/v1", "unexpected role manifest schema")
        self.role = [name for name in manifest["sources"] if Path(name).suffix == ".sv"]
        require(len(self.role) == len(set(self.role)) and set(self.role) ==
                {p.relative_to(ROOT).as_posix() for p in (ROOT / "rtl").glob("*.sv")},
                "role manifest does not give a unique complete SV closure")
        self.runs = []

    def run(self, name, top, *, shell=False, stimulus=(), mutation=None, marker=None, runtime_args=()):
        # A distinct private tree prevents a negative control altering any owned RTL.
        sandbox = self.work / name
        sandbox.mkdir()
        bench = "tests/tb_billet_softshell.sv" if shell else "tests/tb_billet_core.sv"
        hdl = (SHELL[:1] if shell else []) + self.role + (SHELL[1:] if shell else []) + [bench]
        for rel in hdl + list(stimulus):
            src = ROOT / rel if rel in hdl else self.work / rel
            dst = sandbox / rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(src, dst)
        if mutation:
            path, old, new = mutation
            src = (sandbox / path).read_text()
            require(src.count(old) == 1, f"mutation site is not unique: {path}")
            (sandbox / path).write_text(src.replace(old, new))
        argv = [sys.executable, "-m", "vulcan_agent.vulcan_kit.simulation", "--project", str(sandbox),
                "--top", top, "--target", "bedrock-longspeak-arria10", "--timeout-s", "440",
                "--jobs", str(min(4, len(os.sched_getaffinity(0))))]
        for src in hdl + list(stimulus):
            argv += ["--input", src]
        if shell:
            argv += ["--define", "USE_ECC_DDR"]
            for vendor in VENDOR:
                argv += ["--vendor-lib", vendor]
        if stimulus:
            argv += ["--plusarg", "+shell=shell" if shell else "+core=core"]
        for arg in runtime_args:
            argv += ["--plusarg", arg]
        dest = self.retained / name
        dest.mkdir()
        result = subprocess.run(argv, cwd=ROOT, capture_output=True, text=True, timeout=465)
        (dest / "driver.stdout").write_text(result.stdout)
        (dest / "driver.stderr").write_text(result.stderr)
        require(result.returncode in (0, 1),
                f"{name}: simulation driver did not return a receipt, see {dest}")
        receipt = json.loads(result.stdout)
        row = {"name": name, "argv": argv, "exit_code": result.returncode, "directory": str(dest),
               "receipt_sha256": digest(dest / "driver.stdout"), "mutation": mutation}
        self.runs.append(row)
        logs = {}
        for phase, details in receipt["phases"].items():
            for kind in ("stdout", "stderr"):
                path = Path(details[kind])
                shutil.copyfile(path, dest / f"{phase}.{kind}")
            logs[phase] = ((dest / f"{phase}.stdout").read_text() + (dest / f"{phase}.stderr").read_text())
        build = receipt["phases"].get("build", {}).get("result", {})
        run = receipt["phases"].get("run", {}).get("result", {})
        require(receipt["inputs_current"] and build.get("status") == "passed"
                and build.get("process_scope_settled") is True
                and run.get("process_scope_settled") is True,
                f"{name}: no successful compile and settled run, see {dest}")
        if marker:
            require(result.returncode == 1 and run["status"] == "failed" and run["detail"] == "nonzero_exit"
                    and run["exit_code"] in (-signal.SIGABRT, 128 + signal.SIGABRT, 1)
                    and any("%Fatal" in line and marker in line for line in logs["run"].splitlines()),
                    f"{name}: expected a compiled failing run with diagnostic {marker!r}, see {dest}")
            row["failure_witness"] = next(line for line in logs["run"].splitlines()
                                         if "%Fatal" in line and marker in line)
        else:
            require(result.returncode == 0 and run["status"] == "passed",
                    f"{name}: simulation mismatch, see {dest}")
        row["status"] = "expected_failure" if marker else "passed"
        row["input_sha256"] = receipt["input_sha256"]
        return logs["run"], receipt

    def trace(self, receipt, vcd):
        # The admitted kit CLI has no trace flag. Replay its verified, current
        # source snapshot with the same compiler, adding native Verilator tracing.
        sim = Path(receipt["workspace"])
        dest = self.retained / "activity"
        dest.mkdir()
        argv = receipt["phases"]["build"]["argv"].copy()
        argv[1:1] = ["--trace", "--trace-max-array", "256"]
        argv[argv.index("--Mdir") + 1] = "obj_trace"
        argv[argv.index("--top-module") + 1] = "tb_billet_softshell_only"
        command = [str(sim / "obj_trace/sim"), "+shell=shell", "+power", "+trace=activity.vcd"]

        def execute(phase, args, timeout):
            with (dest / f"{phase}.stdout").open("wb") as out, (dest / f"{phase}.stderr").open("wb") as err:
                result = subprocess.run(args, cwd=sim, stdout=out, stderr=err, timeout=timeout)
            require(result.returncode == 0, f"activity {phase} failed, see {dest}")

        row = {"name": "activity", "directory": str(dest), "build_argv": argv, "run_argv": command,
               "inputs": receipt["input_sha256"], "tool": receipt["tool"], "status": "incomplete"}
        self.runs.append(row)
        execute("build", argv, 480)
        execute("run", command, 90)
        require("SHELL_POWER_PASS 256" in (dest / "run.stdout").read_text(),
                "trace did not complete the representative mode 2 waveform and scoreboards")
        raw = sim / "activity.vcd"
        with raw.open("rb") as f:
            header = f.read(65536)
        require(0 < raw.stat().st_size <= 64 * 1024**2 and b"$timescale" in header,
                "missing or out-of-budget native activity VCD")
        with raw.open("rb") as src, vcd.open("xb") as dst:
            shutil.copyfileobj(src, dst)
        row.update(status="passed", sha256=digest(vcd), vcd=str(vcd))


def core_score(output, case_ids):
    pass_rows = [tuple(map(int, x)) for x in re.findall(r"^CORE_PASS (\d+) (\d+) (\d+)$", output, re.M)]
    require(sorted(pass_rows) == [(n, len(case_ids[n]), 3) for n in SIZES],
            "coverage: not every core size, frame, and reset ran")
    quality = {}
    records = {}
    for n in SIZES:
        rows = [list(map(int, x.split())) for x in re.findall(rf"^CORE_FRAME {n} (.+)$", output, re.M)]
        require([r[0] for r in rows] == list(range(len(case_ids[n]))),
                f"N={n} missing checked frame witnesses")
        records[n] = [dict(case=name, kind=r[1], stalled=r[2], first_accept_gap=r[3], cumulative_clamps=r[4])
                      for name, r in zip(case_ids[n], rows, strict=True)]
        bins = re.findall(rf"^CORE_BIN {n} (\d+) ([0-9a-f]{{8}})$", output, re.M)
        require([int(i) for i, _ in bins] == list(range(n)), f"N={n} quality readback incomplete")
        quality[n] = dft_quality(frame(n, "tone"), [unpack(int(v, 16)) for _, v in bins])
        sqnr = quality[n]["sqnr_db"]
        require(quality[n]["cosine"] >= 0.999 and (sqnr is None or sqnr >= 30),
                f"N={n} direct-DFT quality below threshold: {quality[n]}")
    require(records[16][-1]["cumulative_clamps"] == 2**32-1
            and records[256][-2]["cumulative_clamps"] > 0, "clamping or counter saturation was not observed")
    return {"quality": quality, "frames": records, "reset_interruptions_per_size": 3}


def shell_score(output, case_ids):
    modes = {n: [0] * len(case_ids[n]) + [1, 2] for n in case_ids}
    modes[256] += [2, 0, 0]
    accepted = {n: [] for n in case_ids}
    for n, mode, case, fft_cycles, elapsed, csr_cycles, ddr_r, ddr_w, dma_r, dma_w in re.findall(
            r"^SHELL_JOB " + r"(\d+) " * 9 + r"(\d+)$", output, re.M):
        accepted[int(n)].append(dict(mode=int(mode), case=case_ids[int(n)][int(case)],
                                     fft_ddr_cycles=int(fft_cycles), elapsed_ddr_cycles=int(elapsed),
                                     elapsed_csr_cycles=int(csr_cycles),
                                     fft_wrapper_gap_ddr_cycles=int(fft_cycles) -
                                     int(n)*(int(n).bit_length() - 1 + 3),
                                     ddr_read_beats=int(ddr_r), ddr_write_beats=int(ddr_w),
                                     pcie_read_beats=int(dma_r), pcie_write_beats=int(dma_w)))
    for n, rows in accepted.items():
        require([r["mode"] for r in rows] == modes[n], f"N={n} incomplete Shell job matrix")
    require(sorted(map(int, re.findall(r"^SHELL_PASS (\d+)$", output, re.M))) == list(case_ids),
            "SoftShell did not complete at all exercised sizes")
    coverage = re.findall(r"^SHELL_EVENT ([a-z0-9_]+)$", output, re.M)
    require(set(coverage) == {"invalid_descriptors", "abort_ddr", "abort_dma", "dma_fault", "reset_ddr",
                            "reset_dma", "watchdog", "descriptor_snapshot", "completion_hold",
                            "abort_staged_feed"},
            f"missing SoftShell boundary witness: {coverage}")
    return {"jobs": accepted, "events": coverage, "clock_period_ns": {"csr": 10, "ddr": 7, "pcie": 13},
            "fixtures": {"256": "unchanged ECC SoftShell", "2,4,8": "role plus unchanged native DMA CDC"},
            "watchdog": "production parameter; elapsed counter preloaded near terminal count"}


def main():
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument("--check", choices=("behavior", "softshell", "mutations"))
    parser.add_argument("--golden", type=Path, default=ROOT / "tests/billet_golden.json")
    parser.add_argument("--report", type=Path, default=ROOT / "evidence/l1_all.json")
    args = parser.parse_args()
    report = args.report.resolve()
    report.parent.mkdir(parents=True, exist_ok=True)
    if report.exists():
        parser.error(f"report must be a fresh path: {report}")
    retained = Path(tempfile.mkdtemp(prefix=report.stem + "-witnesses-", dir=report.parent))
    data = {"schema": "billet-t1-l1/v1", "status": "failed", "frozen_sha256": digest(args.golden),
            "physical_execution": False, "engineering_acceptance": False, "suites": {}}
    try:
        frozen = frozen_frames(args.golden)
        data["frozen_cases"] = [name for name, _, _ in frozen]
        with tempfile.TemporaryDirectory(prefix="billet-l1-", dir="/tmp") as work:
            work = Path(work)
            runner = Runner(work, retained)
            data["runs"] = runner.runs
            if args.check != "softshell":
                core_cases = core_vectors(work, frozen)
                core_args = dict(stimulus=[f"core{n}.txt" for n in SIZES])
                out, _ = runner.run("core-healthy", "tb_billet_core", **core_args)
                data["suites"]["behavior"] = core_score(out, core_cases)
            if args.check != "behavior":
                shell_cases = shell_vectors(work, frozen)
                shell_args = dict(shell=True, stimulus=[f"shell{n}.txt" for n in shell_cases])
                out, receipt = runner.run("softshell-healthy", "tb_billet_softshell", **shell_args)
                data["suites"]["softshell"] = shell_score(out, shell_cases)
            if args.check in (None, "behavior"):
                for bad in ("n", "log"):
                    runner.run(f"illegal-{bad}", f"tb_billet_illegal_{bad}",
                               marker="PARAMETER ERROR: billet_t1_top")
            if args.check in (None, "softshell"):
                vcd = report.with_name("l1_softshell-activity.vcd")
                runner.trace(receipt, vcd)
            if args.check in (None, "mutations"):
                runner.run("numerical-mutation", "tb_billet_core", **core_args, marker="CORE_NUMERIC",
                           mutation=("rtl/billet_t1_top.sv", "operand_a[31:16] : 16'sd0",
                                     "(operand_a[31:16] ^ 16'h0001) : 16'sd0"))
                runner.run("protocol-mutation", "tb_billet_softshell_only", **shell_args,
                           runtime_args=["+power"], marker="SHELL_PROTOCOL DDR",
                           mutation=("rtl/Role_BilletT1.sv", "assign amm_burstcount = 7'd1;",
                                     "assign amm_burstcount = 7'd2;"))
                data["suites"]["mutations"] = {"compiled_and_rejected": ["numerical", "protocol"]}
            data["status"] = "passed"
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        data["error"] = str(error)
        print(error, file=sys.stderr)
    with report.open("x") as stream:
        json.dump(data, stream, indent=2, allow_nan=False)
        stream.write("\n")
    return int(data["status"] != "passed")


if __name__ == "__main__":
    raise SystemExit(main())
