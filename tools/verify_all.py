"""Run the family contract check and every repository test suite in isolation."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import List, Tuple


ROOT = Path(__file__).resolve().parents[1]

SUITES: List[Tuple[str, Path, List[str]]] = [
    ("Kairos", ROOT, ["tests/"]),
    (
        "Perception",
        ROOT / "brothers" / "01_perception",
        ["instances/tennis_ball/tests/"],
    ),
    (
        "Intent",
        ROOT / "brothers" / "02_intent" / "intent-factory",
        ["instances/cycling/tests/"],
    ),
    (
        "Planning",
        ROOT / "brothers" / "03_planning" / "planning-factory",
        ["instances/cycling/tests/"],
    ),
    ("Sensory/Govern", ROOT / "brothers" / "04_govern", ["tests/"]),
]


def _run(label: str, command: List[str], cwd: Path) -> None:
    print(f"\n[verify_all] {label}", flush=True)
    result = subprocess.run(command, cwd=str(cwd), check=False)
    if result.returncode != 0:
        raise SystemExit(result.returncode)


def main() -> None:
    _run(
        "family contracts",
        [sys.executable, str(ROOT / "tools" / "verify_family.py")],
        ROOT,
    )
    for label, cwd, test_paths in SUITES:
        if not cwd.is_dir():
            raise SystemExit(
                f"[verify_all] Missing {label} checkout at {cwd}. "
                "Initialize submodules before running verification."
            )
        _run(
            label,
            [sys.executable, "-m", "pytest", "-q", *test_paths],
            cwd,
        )
    print("\n[verify_all] All family checks passed.")


if __name__ == "__main__":
    main()
