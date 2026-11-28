#!/usr/bin/env python3
"""Validate the independently authored managed-board inputs without device access."""

import argparse
import hashlib
import json
import math
from pathlib import Path
import sys

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent))
from oracle import board_frames, fft, frame, pack, packed_bytes


ROOT = Path(__file__).resolve().parents[1]
REFERENCE = "platform-inputs/netsys17/host-board-reference.json"
CONFIG = "tests/platform_config.json"
PLAN = "fpga/board_hil.json"
ORACLE = "tests/oracle.py"
ORACLE_SHA256 = "3fdb95d8486e1eb861c1cb329dfb16f40a48390da0ad5000fc5852a251bd5eb4"
MAGIC = "0x42494c4c45545431"
N = 256
RUNS = 3
LEGACY_VECTORS = {
    "impulse": ("48e5f075a462354a779c91e0c63921707ad703cfb385a020fd7266bb02c07158",
                "efc433fa5f35f46f1b418da55eb167098ebc6bcb91a44c4cc2e9c1cf6bd9b118"),
    "tone": ("6c72e57dff7164d19f313a3c2121815e7615345f211429b69fa68482b744ca94",
             "3ab7165016fb2686cc4326357d89d35330fad902c4cc478491e55fbd1cd42ba2"),
    "broadband": ("45aba64e0ee8100f68da455e1b0dfc2257c4caf3cde366985f60a33f04bfb5d9",
                  "751986146067efd0870e9b7c619018582c84589660993f17e00b7d191d9e0244"),
}
COHERENT_BINS = (1, 7, 63, 127)
VECTOR_IDS = (*LEGACY_VECTORS, "dc", "nyquist", *(f"tone_bin_{k}" for k in COHERENT_BINS),
              "adjacent_31_32", "quadrature", "chirp", "rails", "conjugate_symmetry", "serialized_16")


def require(ok, message):
    if not ok:
        raise ValueError(message)


def sha(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def binding(path):
    artifact = (ROOT / path).resolve(strict=True)
    require(artifact == ROOT / path and artifact.is_file(), f"invalid board input path {path}")
    return {"path": path, "sha256": sha(artifact)}


def vector_path(name, extension):
    return f"tests/board_vectors/{name}.{extension}"


def polar(amplitude, angle):
    return round(amplitude * math.cos(angle)), round(amplitude * math.sin(angle))


def tone(bin_index, amplitude, phase=0):
    return [polar(amplitude, math.tau * (bin_index * j % N) / N + phase) for j in range(N)]


def merge_tones(a, b):
    return [(ar + br, ai + bi) for (ar, ai), (br, bi) in zip(a, b)]


def serialized_frames():
    frames = []
    for i in range(16):
        if i == 6:
            burst_rails = tone(3, 16000, 0.29)
            samples = [tuple(32767 if part >= 0 else -32768 for part in sample) for sample in burst_rails]
        elif i % 4 == 0:
            samples = tone(5 + 2*i, 9000 + 300*i, 0.19*i)
        elif i % 4 == 1:
            samples = frame(N, "broadband", seed=0x5E7100 + i)
        elif i % 4 == 2:
            samples = merge_tones(tone(12 + i, 11000, 0.31), tone(29 + i, 6000, -0.17))
        else:
            samples = [(0, 0)] * N
            samples[7*i] = (19000 + 100*i, -18000)
            samples[N - 5*i] = (-10000, 7000 + 150*i)
        frames.append(samples)
    return frames


def spectral_frames():
    real_tones = merge_tones(tone(17, 13000, 0.29), tone(55, 5000, -0.64))
    single = {
        **board_frames(),
        "dc": [(15000, -7000)] * N,
        "nyquist": [(13000, 5000) if j % 2 == 0 else (-13000, -5000) for j in range(N)],
        **{f"tone_bin_{k}": tone(k, 12000, 0.21) for k in COHERENT_BINS},
        "adjacent_31_32": merge_tones(tone(31, 12000, 0.31), tone(32, 7000, -0.19)),
        "quadrature": [(-im, re) for re, im in tone(11, 13000)],
        "chirp": [polar(14000, math.tau * (4 * t + 45 * t*t) + 0.13)
                  for t in (j / N for j in range(N))],
        "rails": frame(N, "rails"),
        "conjugate_symmetry": [(re, 0) for re, _ in real_tones],
    }
    return {**{name: [samples] for name, samples in single.items()}, "serialized_16": serialized_frames()}


def board_plan(reference):
    template = reference["board_hil_json_contract"]["required_top_level_fields"]
    collector = template["native_collector"]
    oracle = binding(ORACLE)
    require(oracle["sha256"] == ORACLE_SHA256, "shared independent FFT oracle changed")
    return {
        "expected_magic_hex": MAGIC, "runs": RUNS,
        "native_collector": {
            "argv": collector["argv"], "managed_board_owner": True, "timeout_s": 4800,
            "configuration": binding(CONFIG), "dma_ownership": collector["dma_ownership"],
            "api_sources": [binding(REFERENCE)],
            "workload_sources": {"business_script": binding("tests/business-test.ps1"),
                                 "companion": binding("tests/Workload.cs")},
        },
        "experiment_plan": {
            "protocol": "reviewed-native-v1", "workload_protocol": "softreg-readback/v1",
            "vectors": [{
                "id": name, "input": binding(vector_path(name, "json")),
                "expected": binding(vector_path(name, "bin")), "oracle_source": oracle,
                "comparison": {"format": "bytes"},
            } for name in VECTOR_IDS],
        },
    }


def check_spectra(spectra, clamp_plan):
    for name, bins in {"dc": (0,), "nyquist": (128,), "adjacent_31_32": (31, 32),
                       "quadrature": (11,), **{f"tone_bin_{k}": (k,) for k in COHERENT_BINS}}.items():
        energy = [re*re + im*im for re, im in spectra[name]]
        require(all(energy[k] >= 6000**2 for k in bins)
                and max(e for k, e in enumerate(energy) if k not in bins) <= 16**2,
                f"{name} spectrum does not resolve its intended bins")
    re, im = spectra["quadrature"][11]
    require(abs(re) <= 16 and im >= 12980, "quadrature lacks the expected +90 degree phase")
    chirp_energy = [re*re + im*im for re, im in spectra["chirp"]]
    require(sum(chirp_energy[4:95]) >= 0.9 * sum(chirp_energy)
            and sum(e >= 500**2 for e in chirp_energy) >= 64, "chirp lacks a broad sweep in its target band")
    conjugate = spectra["conjugate_symmetry"]
    require(all(abs(re - conjugate[-k][0]) <= 16 and abs(im + conjugate[-k][1]) <= 16
                for k, (re, im) in enumerate(conjugate)) and abs(conjugate[0][1]) <= 8,
            "real-input spectrum is not conjugate symmetric within fixed-point rounding")
    increments = {row["id"]: row["increments"] for row in clamp_plan}
    require(increments["rails"][0] > 0 and any(increments["serialized_16"][1:-1]),
            "rail stimulus must exercise clamp increments in isolation and within the burst")


def check_workload_clamps(clamp_plan):
    source = (ROOT / "tests/business-test.ps1").read_text()
    _, marker, tail = source.partition("$clampPlan = ConvertFrom-Json -InputObject @'\n")
    raw, end, _ = tail.partition("\n'@")
    require(marker and end and json.loads(raw) == clamp_plan,
            "business workload per-frame clamp schedule differs from the independent oracle")


def verify_vectors(plan):
    suite = spectral_frames()
    require(tuple(suite) == VECTOR_IDS, "independent spectral matrix is out of order")
    input_digests, output_digests, rows, projected_vectors, clamp_plan = set(), set(), [], [], []
    spectra = {}
    for entry in plan["experiment_plan"]["vectors"]:
        name = entry["id"]
        if name in LEGACY_VECTORS:
            require((entry["input"]["sha256"], entry["expected"]["sha256"]) == LEGACY_VECTORS[name],
                    f"original {name} payload bytes changed")
        vector = json.loads((ROOT / entry["input"]["path"]).read_text())
        values = vector["inputs"]
        frames = suite[name]
        count = 16 if name == "serialized_16" else 1
        require(set(vector) == {"inputs"} and isinstance(values, list) and len(frames) == count
                and len(values) == count*N and all(type(v) is int and 0 <= v < 2**32 for v in values)
                and values == [pack(x) for samples in frames for x in samples],
                f"incorrect packed input words or frame order for {name}")
        raw = (ROOT / entry["expected"]["path"]).read_bytes()
        require(len(raw) == count*N*4, f"incorrect expected byte count for {name}")
        observations = []
        for i, samples in enumerate(frames):
            expected, clamps = fft(samples)
            observed = raw[i*N*4:(i+1)*N*4]
            require(len(samples) == N and any(values[i*N:(i+1)*N]) and observed == packed_bytes(expected),
                    f"{name}[{i}] differs from the independent Q1.15 spectrum")
            inhash = hashlib.sha256(packed_bytes(samples)).hexdigest()
            outhash = hashlib.sha256(observed).hexdigest()
            require(inhash not in input_digests and outhash not in output_digests,
                    f"{name}[{i}] duplicates another input frame or spectrum")
            input_digests.add(inhash)
            output_digests.add(outhash)
            observations.append({"frame_index": i, "input_words_sha256": inhash,
                                 "expected_sha256": outhash, "expected_component_clamps": clamps})
        if count == 1:
            spectra[name] = expected
        rows.append({"id": name, "input_words": len(values), "expected_bytes": len(raw), "frames": observations})
        projected_vectors.append({"id": name, "inputs": values})
        clamp_plan.append({"id": name, "increments": [f["expected_component_clamps"] for f in observations]})
    check_spectra(spectra, clamp_plan)
    check_workload_clamps(clamp_plan)
    return rows, projected_vectors


def check_novelty(plan, history):
    # The historical platform qualification is MUL16, not the preceding Billet suite.
    prior = json.loads((ROOT / history["prior_campaign"]["path"]).read_text())
    parent = prior.get("experiment_plan")
    parent_ids = set(LEGACY_VECTORS)
    parent_inputs = {digests[0] for digests in LEGACY_VECTORS.values()}
    if parent is not None:
        parent_ids.update(v["id"] for v in parent["vectors"])
        parent_inputs.update(v["input"]["sha256"] for v in parent["vectors"])
    else:
        prior_result = json.loads((ROOT / history["prior_campaign_result"]["path"]).read_text())
        require(prior["qualification_profile"] == "pioneer-mul16-a/v1"
                and "products" in prior_result["campaign"]["physical_result"],
                "bound prior workload is not the recognized MUL16 qualification or a declared vector suite")
    novel = [v["id"] for v in plan["experiment_plan"]["vectors"]
             if v["id"] not in parent_ids and v["input"]["sha256"] not in parent_inputs]
    require(2 * len(novel) >= len(VECTOR_IDS), "fewer than half the board vectors are generation-novel")
    return novel


def verify():
    reference = json.loads((ROOT / REFERENCE).read_text())
    require(reference["schema"] == "netsys17-softreg-board-hil-reference/v2", "wrong managed board API")
    contract = reference["platform_config_template"]
    config = json.loads((ROOT / CONFIG).read_text())
    require(config == contract and config["original_app1_magic"] == "0x4655524e41435831",
            "managed config differs from the exact NETSYS17 template or App1 identity")
    entry = reference["collector_entrypoint"]
    require((ROOT / entry["path"]).read_text() == entry["exact_python_source"],
            "collector is not the exact runtime-delegating entrypoint")
    history = {}
    for key in ("prior_campaign", "prior_campaign_result", "prior_image"):
        row = binding(config[key])
        expected = reference["prior_image_sha256"] if key == "prior_image" else config[f"{key}_sha256"]
        require(row["sha256"] == expected, f"historical reference {key} digest mismatch")
        history[key] = row
    plan = json.loads((ROOT / PLAN).read_text())
    require(plan == board_plan(reference), "board plan does not match hash-bound NETSYS17 and vector inputs")
    rows, vectors = verify_vectors(plan)
    novel = check_novelty(plan, history)
    stress = [v["id"] for v in rows if v["input_words"] >= 128 or v["expected_bytes"] >= 512]
    comparisons = RUNS * len(vectors)
    frames = RUNS * sum(len(v["frames"]) for v in rows)
    require(len(stress) >= 2 and (comparisons, frames) == (45, 90), "wrong stress scale or campaign size")
    from vulcan_agent.board_campaign import SOFTREG_PROTOCOL, workload_payload, workload_vectors

    projected = workload_payload(plan, SOFTREG_PROTOCOL, workload_vectors(ROOT, plan, SOFTREG_PROTOCOL))
    require(projected == {"schema": 1, "workload_protocol": "softreg-readback/v1",
                          "runs": [{"vectors": vectors} for _ in range(RUNS)]},
            "runtime workload projection did not preserve the admitted 3x15 matrix and frame order")
    return {"vectors": rows, "plan": binding(PLAN), "history": history, "device_access": False,
            "runs": RUNS, "vector_comparisons": comparisons, "frames": frames,
            "stress_vector_ids": stress, "generation_novel_ids": novel,
            "expected_role_magic": MAGIC, "expected_app1_magic": config["original_app1_magic"],
            "scope": "Offline source/vector bindings only; no Windows compile, image, transport, or restoration evidence."}


def main():
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    if args.report.exists():
        parser.error(f"report must be a fresh path: {args.report}")
    report = {"schema": "billet-board-contract/v1", "status": "failed", "engineering_acceptance": False}
    try:
        report.update(verify(), status="passed")
    except (OSError, ValueError, KeyError, TypeError) as error:
        report["error"] = str(error)
        print(error, file=sys.stderr)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    with args.report.open("x") as stream:
        json.dump(report, stream, indent=2)
        stream.write("\n")
    return int(report["status"] != "passed")


if __name__ == "__main__":
    raise SystemExit(main())
