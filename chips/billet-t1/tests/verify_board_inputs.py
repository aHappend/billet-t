#!/usr/bin/env python3
"""Validate the independently authored managed-board inputs without device access."""

import argparse
import hashlib
import json
from pathlib import Path
import sys

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent))
from oracle import board_frames, fft, pack, packed_bytes


ROOT = Path(__file__).resolve().parents[1]
REFERENCE = "platform-inputs/netsys17/host-board-reference.json"
CONFIG = "tests/platform_config.json"
PLAN = "fpga/board_hil.json"
ORACLE = "tests/oracle.py"
MAGIC = "0x42494c4c45545431"


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


def board_plan(reference):
    template = reference["board_hil_json_contract"]["required_top_level_fields"]
    collector = template["native_collector"]
    return {
        "expected_magic_hex": MAGIC, "runs": 3,
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
                "expected": binding(vector_path(name, "bin")), "oracle_source": binding(ORACLE),
                "comparison": {"format": "bytes"},
            } for name in board_frames()],
        },
    }


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
    input_digests, output_digests, rows = set(), set(), []
    for name, samples in board_frames().items():
        vector = json.loads((ROOT / vector_path(name, "json")).read_text())
        values = vector["inputs"]
        require(set(vector) == {"inputs"} and len(values) == 256
                and all(type(v) is int and 0 <= v < 2**32 for v in values)
                and values == [pack(x) for x in samples] and any(values), f"bad independent inputs for {name}")
        raw = (ROOT / vector_path(name, "bin")).read_bytes()
        expected, clamps = fft(samples)
        require(len(raw) == 1024 and raw == packed_bytes(expected),
                f"expected file for {name} differs from independent Q1.15 output bytes")
        inhash = hashlib.sha256(packed_bytes(samples)).hexdigest()
        outhash = hashlib.sha256(raw).hexdigest()
        require(inhash not in input_digests and outhash not in output_digests, "duplicate board vector")
        input_digests.add(inhash)
        output_digests.add(outhash)
        rows.append({"id": name, "input_words_sha256": inhash, "expected_sha256": outhash,
                     "output_bins": len(expected), "expected_component_clamps": clamps})
    from vulcan_agent.board_campaign import SOFTREG_PROTOCOL, workload_payload, workload_vectors

    projected = workload_payload(plan, SOFTREG_PROTOCOL, workload_vectors(ROOT, plan, SOFTREG_PROTOCOL))
    require(len(projected["runs"]) == 3 and all(len(r["vectors"]) == 3 for r in projected["runs"]),
            "runtime workload projection did not preserve the admitted 3x3 matrix")
    return {"vectors": rows, "plan": binding(PLAN), "history": history, "device_access": False,
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
