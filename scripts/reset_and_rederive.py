"""Reset every derived output and derive it again from the raw data, then check nothing moved.

Run before a release and after anything that touched the running system, such as
recording the demo: the published figures must be what a fresh clone of the documented
setup reproduces, not what a session happened to leave behind. The raw generated data
and the fetched public files are inputs and are kept; everything after them is rebuilt.

The run fails if a gate fails or if any committed result differs afterwards. Documents
must match byte for byte. Data files are compared by content, with floats allowed to
move by one part in a billion, because DuckDB and Polars sum in parallel and in no fixed
order; a data file that moved only that much is put back to its committed bytes so the
tree stays clean, and the run says how many there were.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ledger_functions.reproduce import TOLERANCE, reproduced

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
COMMITTED = ["results", "README.md", "RESULTS.md", "docs", "report", "web/public/data"]


def run(cmd: list[str]) -> None:
    print("+", " ".join(cmd), flush=True)
    subprocess.run(cmd, cwd=ROOT, check=True)


def compare(root: Path = ROOT) -> tuple[list[str], list[str]]:
    """Paths that moved, and paths that moved only by float noise (restored)."""
    status = subprocess.run(
        ["git", "status", "--porcelain", "--untracked-files=all", "--", *COMMITTED],
        cwd=root,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.splitlines()
    moved: list[str] = []
    noise: list[str] = []
    for line in status:
        code, path = line[:2], line[3:]
        if code.strip() != "M":
            moved.append(line)
            continue
        committed = subprocess.run(
            ["git", "show", f"HEAD:{path}"], cwd=root, capture_output=True, check=True
        ).stdout
        if reproduced(root / path, committed):
            subprocess.run(["git", "checkout", "--", path], cwd=root, check=True)
            noise.append(path)
        else:
            moved.append(line)
    return moved, noise


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
    moved, noise = compare()
    if noise:
        print(f"{len(noise)} data files moved only below a relative {TOLERANCE:g} and were restored")
    if moved:
        print("rederived outputs differ from the committed ones:\n" + "\n".join(moved))
        return 1
    print("rederived: every committed result reproduced")
    return 0


if __name__ == "__main__":
    sys.exit(main())
