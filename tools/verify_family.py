"""
verify_family.py — Check that all brothers satisfy CONTRACT_FAMILY.md invariants.

Runs without arguments from the kairos-factory root:
    python3 tools/verify_family.py

Checks:
  1. Each brother directory has a CONTRACT.md
  2. Each CONTRACT.md declares a confidence vocabulary (DATA_LABEL or vocabulary keyword)
  3. Each CONTRACT.md mentions latency (Guardrail 8)
  4. Built brothers (those with test directories) have at least one test file
"""

import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
BROTHERS_DIR = ROOT / "brothers"

REQUIRED_VOCABULARY_KEYWORDS = [
    "MEASURED", "TRACKED", "PREDICTED",   # perception-factory
    "REAL", "PROXY", "DECLARED",          # sensory-architecture-factory
    "DATA_LABEL",                          # scaffold placeholder
    "vocabulary",
]

LATENCY_KEYWORDS = ["LATENCY", "latency", "dt_ahead", "latency_ms"]


def check_brother(path: Path) -> list[str]:
    issues = []
    name = path.name

    # Accept CONTRACT.md at root or anywhere within the brother directory
    contracts = list(path.rglob("CONTRACT.md"))
    if not contracts:
        issues.append(f"[{name}] Missing CONTRACT.md (checked recursively)")
        return issues

    # Concatenate all contract files for keyword checks
    text = "\n".join(c.read_text(encoding="utf-8") for c in contracts)

    if not any(kw in text for kw in REQUIRED_VOCABULARY_KEYWORDS):
        issues.append(f"[{name}] CONTRACT.md missing confidence vocabulary declaration")

    if not any(kw in text for kw in LATENCY_KEYWORDS):
        issues.append(f"[{name}] CONTRACT.md missing latency documentation (Guardrail 8)")

    test_dirs = list(path.rglob("tests/"))
    if test_dirs:
        test_files = [f for d in test_dirs for f in d.glob("test_*.py")]
        if not test_files:
            issues.append(f"[{name}] Has tests/ directory but no test_*.py files")

    return issues


def main() -> int:
    if not BROTHERS_DIR.exists():
        print(f"[verify_family] brothers/ directory not found at {BROTHERS_DIR}")
        return 1

    brothers = sorted(p for p in BROTHERS_DIR.iterdir() if p.is_dir())
    if not brothers:
        print("[verify_family] No brother directories found.")
        return 1

    all_issues = []
    for b in brothers:
        issues = check_brother(b)
        all_issues.extend(issues)

    if all_issues:
        print("[verify_family] ISSUES FOUND:")
        for issue in all_issues:
            print(f"  {issue}")
        return 1

    print(f"[verify_family] All {len(brothers)} brothers pass family contract checks.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
