"""Retain one bounded preparation smoke; never substitutes for runtime checks."""
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
import sys
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parent))
from verify import ROOT, source_hashes

out = ROOT / "evidence/preparation" / ("verifier-smoke-" + uuid.uuid4().hex[:12])
out.mkdir(parents=True)
argv = [sys.executable, "tests/verify.py", "--check", "behavior",
        "--output-dir", str(out / "run"), "--preparation-smoke"]
receipt = {"argv": argv, "cwd": str(ROOT), "source_sha256": source_hashes(),
           "tool_version": sys.version,
           "started_at": datetime.now(timezone.utc).isoformat(),
           "timeout_s": 7200,
           "stdout": str((out/"stdout.log").relative_to(ROOT)),
           "stderr": str((out/"stderr.log").relative_to(ROOT))}
if len(sys.argv) > 1:
    receipt["repair_of"] = sys.argv[1]
try:
    with (out/"stdout.log").open("w") as so, (out/"stderr.log").open("w") as se:
        proc = subprocess.run(argv, cwd=ROOT, stdout=so, stderr=se, timeout=7200)
    receipt.update(exit_code=proc.returncode, timed_out=False)
except subprocess.TimeoutExpired:
    receipt.update(exit_code=None, timed_out=True)
finally:
    receipt["ended_at"] = datetime.now(timezone.utc).isoformat()
    (out/"receipt.json").write_text(json.dumps(receipt, indent=2)+"\n")
    print(str((out/"receipt.json").relative_to(ROOT)))
sys.exit(receipt["exit_code"] if receipt["exit_code"] is not None else 1)
