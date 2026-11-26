#!/usr/bin/env python3
"""Matched Q1.15 FFT corpus, native baselines, and CUDA inventory."""

import argparse
import csv
import hashlib
import json
import math
import os
from pathlib import Path
import re
import shutil
import statistics
import subprocess
import sys
import tempfile

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent))
from oracle import board_frames, fft, frame, packed_bytes, twiddles


ROOT = Path(__file__).resolve().parents[1]
NVCC = Path("/usr/local/cuda-12.8/bin/nvcc")
N = 256
BATCHES = (1, 16, 256)
WARMUPS = 5
REPS = 30


def sha(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def run(argv, timeout, *, affinity=None):
    command = [str(x) for x in argv]
    pin = (lambda: os.sched_setaffinity(0, affinity)) if affinity is not None else None
    result = subprocess.run(command, cwd=ROOT, preexec_fn=pin, capture_output=True, text=True, timeout=timeout)
    if result.returncode:
        raise ValueError(f"{command}: exit {result.returncode}\n{result.stderr}\n{result.stdout}")
    return result.stdout.strip()


def corpus(path):
    physical = list(board_frames().values())
    frames = physical + [frame(N, "rails")] + [frame(N, "broadband", 0x661A00 + i) for i in range(252)]
    inputs = b"".join(packed_bytes(x) for x in frames)
    golden = b"".join(packed_bytes(fft(x)[0]) for x in frames)
    coefficients = packed_bytes(twiddles(N))
    path.write_bytes(coefficients + inputs + golden)
    return {
        "fft_points": N, "frames": len(frames),
        "layout": "Q1.15 little endian per complex lane, real then imag; natural sample/bin order",
        "corpus_binary_layout": "128 forward twiddles, 256 input frames, 256 expected frames",
        "seed_start": 0x661A00, "first_frames": ["board_impulse", "board_tone", "board_broadband", "clipping_rails"],
        "batch_selection": "prefix of identical ordered corpus",
        "corpus_sha256": sha(path),
        "batch_input_sha256": {batch: hashlib.sha256(inputs[:batch*N*4]).hexdigest() for batch in BATCHES},
        "expected_bins_sha256": hashlib.sha256(golden).hexdigest(),
        "twiddle_sha256": hashlib.sha256(coefficients).hexdigest(),
        "oracle_sha256": sha(ROOT / "tests/oracle.py"),
    }


def timing_cells(stdout):
    lines = stdout.splitlines()
    if not lines or lines[0] != f"verified {N * BATCHES[-1]}":
        raise ValueError("benchmark executable did not verify every bin before timing")
    timings = {(batch, boundary): [] for batch in BATCHES
               for boundary in ("kernel_only", "transfer_inclusive")}
    for row in lines[1:]:
        batch, boundary, value = row.split()
        timings[int(batch), boundary].append(int(value))
    cells = []
    for (batch, boundary), ns in timings.items():
        if len(ns) != REPS or any(t <= 0 for t in ns):
            raise ValueError(f"invalid positive timing sample count for {batch}/{boundary}")
        cells.append({"batch": batch, "boundary": boundary, "raw_ns": ns, "median_ns": statistics.median(ns),
                      "p95_ns": sorted(ns)[math.ceil(len(ns) * .95)-1]})
    return cells


def cpu(work):
    compiler = Path(shutil.which("g++") or "g++").resolve(strict=True)
    src = ROOT / "tests/matched_cpu.cpp"
    exe, binary = work / "matched_cpu", work / "corpus.bin"
    workload = corpus(binary)
    command = [compiler, "-std=c++17", "-O3", "-march=native", "-Wall", "-Wextra", "-Werror", src, "-o", exe]
    run(command, 90)
    eligible = sorted(os.sched_getaffinity(0))
    model = next((line.split(":", 1)[1].strip() for line in Path("/proc/cpuinfo").read_text().splitlines()
                  if line.startswith("model name") and ":" in line), os.uname().machine)
    affinity = {eligible[0]}
    times = timing_cells(run([exe, binary], 600, affinity=affinity))
    return {
        "workload": workload, "source_sha256": sha(src), "executable_sha256": sha(exe),
        "compile_argv": list(map(str, command)), "compiler": {"path": str(compiler), "sha256": sha(compiler),
                                                             "version": run([compiler, "--version"], 10)},
        "device": {"model": model, "logical_cpu_affinity": sorted(affinity),
                   "eligible_logical_cpus": eligible, "threads": 1},
        "correctness": {"comparison": "exact independently modeled output words", "bins": N*BATCHES[-1]},
        "boundaries": {"kernel_only": "host-resident input through host-resident output, including complete FFT",
                       "transfer_inclusive": "host-to-host stage input, same FFT, then host-to-host copy output"},
        "timer": "std::chrono::steady_clock", "warmups_per_cell": WARMUPS,
        "timed_repetitions_per_cell": REPS, "cells": times,
    }


def inventory(nvcc):
    if nvcc != NVCC:
        raise ValueError(f"CUDA compiler must be pinned to {NVCC}")
    version = run([nvcc, "--version"], 15)
    if "release 12.8," not in version:
        raise ValueError("pinned nvcc did not identify itself as CUDA 12.8")
    codes = run([nvcc, "--list-gpu-code"], 15).splitlines()
    fields = ("index", "uuid", "name", "driver_version", "memory.total", "compute_cap")
    cli = ["nvidia-smi", "--query-gpu=" + ",".join(fields), "--format=csv,noheader,nounits"]
    # Inventory is intentionally read-only; GPU benchmarking is separately UUID-admitted.
    raw = run(cli, 30)
    devices = []
    for row in csv.reader(raw.splitlines(), skipinitialspace=True):
        index, uuid, name, driver, memory, capability = [v.strip() for v in row]
        if not re.fullmatch(r"GPU-[0-9a-fA-F-]{36}", uuid) or not re.fullmatch(r"\d+\.\d+", capability):
            raise ValueError(f"unrecognized device identity {uuid!r}/{capability!r}")
        devices.append({"index": int(index), "gpu_uuid": uuid, "name": name, "driver_version": driver,
                        "memory_mib": int(memory), "compute_capability": capability,
                        "nvcc_native_code_supported": "sm_" + capability.replace(".", "") in codes})
    if len({d["gpu_uuid"] for d in devices}) != len(devices) or not any(
            d["nvcc_native_code_supported"] for d in devices):
        raise ValueError("no uniquely identifiable native CUDA 12.8 candidate GPU")
    return {"argv": cli, "raw_csv": raw, "compiler": {"path": str(nvcc), "sha256": sha(nvcc), "version": version,
                                                     "native_codes": codes}, "devices": devices}


def gpu(work, nvcc):
    # A separate, UUID-pinned check must be admitted after the inventory receipt.
    receipt = ROOT / "evidence/gpu_inventory.json"
    selected = os.environ.get("CUDA_VISIBLE_DEVICES")
    if not selected or not re.fullmatch(r"GPU-[0-9a-fA-F-]{36}", selected):
        raise ValueError("the managed CUDA check must expose exactly one admitted GPU UUID")
    inventory_doc = json.loads(receipt.read_text())
    compiler = inventory_doc["compiler"]
    if (inventory_doc["backend"] != "inventory" or inventory_doc["status"] != "passed"
            or nvcc != NVCC or str(nvcc) != compiler["path"] or sha(nvcc) != compiler["sha256"]
            or run([nvcc, "--version"], 15) != compiler["version"]):
        raise ValueError("native compiler differs from the admitted CUDA 12.8 inventory")
    devices = [d for d in inventory_doc["devices"] if d["gpu_uuid"] == selected and d["nvcc_native_code_supported"]]
    if len(devices) != 1:
        raise ValueError(f"GPU {selected} is not a unique compatible candidate in the bound inventory")
    src = ROOT / "tests/matched_gpu.cu"
    if not src.is_file():
        raise ValueError("the separately assigned native CUDA companion is not present")
    exe, binary = work / "matched_gpu", work / "corpus.bin"
    workload = corpus(binary)
    arch = devices[0]["compute_capability"].replace(".", "")
    command = [nvcc, "-std=c++17", "-O3", f"-arch=sm_{arch}", "-Xcompiler=-O3", src, "-o", exe]
    run(command, 180)
    stdout = run([exe, binary, selected], 780)
    identity, separator, timings = stdout.partition("\n")
    actual = json.loads(identity)
    if not separator or actual["gpu_uuid"] != selected or actual["compute_capability"] != devices[0]["compute_capability"]:
        raise ValueError("native CUDA runtime did not observe the selected UUID and compute capability")
    return {
        "workload": workload, "source_sha256": sha(src), "executable_sha256": sha(exe),
        "compile_argv": list(map(str, command)), "compiler": compiler, "inventory_sha256": sha(receipt),
        "device": {**devices[0], **actual}, "host_cpu_affinity": sorted(os.sched_getaffinity(0)), "host_cpu_threads": 1,
        "correctness": {"comparison": "exact independently modeled output words", "bins": N*BATCHES[-1]},
        "boundaries": {"kernel_only": "CUDA events around FFT with device-resident input/output",
                       "transfer_inclusive": "host monotonic clock around input H2D, FFT, output D2H and sync"},
        "warmups_per_cell": WARMUPS, "timed_repetitions_per_cell": REPS, "cells": timing_cells(timings),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument("--backend", choices=("cpu", "inventory", "gpu"), required=True)
    parser.add_argument("--nvcc", type=Path, default=NVCC)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    if args.report.exists():
        parser.error(f"report must be a fresh path: {args.report}")
    report = {"schema": "billet-matched-baseline/v1", "backend": args.backend,
              "status": "failed", "engineering_acceptance": False}
    try:
        if args.backend == "inventory":
            report.update(inventory(args.nvcc))
        else:
            with tempfile.TemporaryDirectory(prefix=f"billet-{args.backend}-", dir="/tmp") as work:
                report.update(cpu(Path(work)) if args.backend == "cpu" else gpu(Path(work), args.nvcc))
        report["status"] = "passed"
    except (OSError, ValueError, KeyError, subprocess.SubprocessError) as error:
        report["error"] = str(error)
        print(error, file=sys.stderr)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    with args.report.open("x") as stream:
        json.dump(report, stream, indent=2, allow_nan=False)
        stream.write("\n")
    return int(report["status"] != "passed")


if __name__ == "__main__":
    raise SystemExit(main())
