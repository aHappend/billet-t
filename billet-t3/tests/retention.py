"""Project-local immutable execution receipts, shared by checks and diagnostics."""
import datetime
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import time

ROOT = Path(__file__).resolve().parents[1]
INPUTS = ("rtl/*.sv", "design/SPEC.md", "design/ARCHITECTURE.md",
          "tests/*.py", "billet_t2_reference/rtl/*.sv")


def stamp():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def hashes():
    files = sorted({p for pattern in INPUTS for p in ROOT.glob(pattern)})
    for pattern in INPUTS:
        if not list(ROOT.glob(pattern)):
            raise RuntimeError(f"Empty required source selector: {pattern}")
    return {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in files}


def write(path, value):
    path.write_text(json.dumps(value, indent=2) + "\n")


class Run:
    def __init__(self, directory, argv, repair_of=None):
        self.directory = Path(directory).resolve()
        self.directory.mkdir(parents=True, exist_ok=False)
        self.receipt = {"argv": argv, "cwd": str(ROOT), "start": stamp(),
                        "source_sha256": hashes(), "executions": [],
                        "repair_of": repair_of, "acceptance_evidence": False}
        self.versions = {}
        self.result = None
        snapshots = self.directory / "sources"
        for name in self.receipt["source_sha256"]:
            dest = snapshots / name
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ROOT / name, dest)

    def execute(self, label, argv, timeout=7200):
        start, mono = stamp(), time.monotonic()
        out = self.directory / (label + ".stdout.log")
        err = self.directory / (label + ".stderr.log")
        record = {"argv": [str(a) for a in argv], "cwd": str(ROOT),
                  "start": start, "timeout_s": timeout,
                  "stdout": str(out.relative_to(ROOT)),
                  "stderr": str(err.relative_to(ROOT))}
        self.receipt["executions"].append(record)
        try:
            with out.open("wb") as stdout, err.open("wb") as stderr:
                result = subprocess.run(argv, cwd=ROOT, stdout=stdout, stderr=stderr,
                                        timeout=timeout, check=False)
            record.update(exit_code=result.returncode, timed_out=False)
            if result.returncode:
                raise RuntimeError(f"{label} exited {result.returncode}: {err}")
        except subprocess.TimeoutExpired:
            record.update(exit_code=None, timed_out=True)
            raise
        except OSError as e:
            record.update(exit_code=None, timed_out=False, execution_error=str(e))
            raise
        finally:
            record.update(end=stamp(), duration_s=time.monotonic() - mono)
        return out

    def version(self, tool):
        argv = [tool, "-V"] if tool != "python3" else [tool, "--version"]
        if tool == "vvp":
            argv = [tool, "-V"]
        path = self.execute("version-" + tool, argv)
        self.versions[tool] = path.read_text() + (
            self.directory / ("version-" + tool + ".stderr.log")).read_text()

    def finish(self, status, result=None, error=None):
        self.receipt.update(end=stamp(), status=status, tool_versions=self.versions,
                            error=error)
        if result is not None:
            write(self.directory / "results.json", result)
        write(self.directory / "receipt.json", self.receipt)
