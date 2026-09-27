"""Reset every derived output and derive it again from the raw data, then check nothing moved.

Run before a release and after anything that touched the running system, such as
recording the demo: the published figures must be what a fresh clone of the documented
setup reproduces, not what a session happened to leave behind. The raw generated data
and the fetched public files are inputs and are kept; everything after them is rebuilt.
The run fails if a gate fails or if any committed result differs afterwards.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STAGES = [
    "contracts",
    "warehouse",
    "reconcile",
    "metrics",
    "models",
    "functions",
    "manifest",
    "render",
    "export",
    "site-data",
]
DERIVED = ["data/staged", "data/quarantine", "warehouse/target"]
GATES = [
    "scripts/check_published_numbers.py",
    "scripts/check_no_em_dash.py",
    "scripts/check_vocabulary.py",
    "scripts/check_statements.py",
    "scripts/check_bank_name.py",
    "scripts/scan_for_planted_identifiers.py",
]


def run(cmd: list[str]) -> None:
    print("+", " ".join(cmd), flush=True)
    subprocess.run(cmd, cwd=ROOT, check=True)


def main() -> int:
    for folder in DERIVED:
        path = ROOT / folder
        if path.exists():
            for child in path.iterdir():
                if child.name != ".gitkeep":
                    shutil.rmtree(child) if child.is_dir() else child.unlink()
    for stage in STAGES:
        run(["make", stage])
    for gate in GATES:
        run(["uv", "run", "python", gate])
    changed = subprocess.run(
        [
            "git",
            "status",
            "--porcelain",
            "--",
            "results",
            "README.md",
            "RESULTS.md",
            "docs",
            "report",
            "web/public/data",
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    if changed:
        print("rederived outputs differ from the committed ones:\n" + changed)
        return 1
    print("rederived: every committed result reproduced")
    return 0


if __name__ == "__main__":
    sys.exit(main())
