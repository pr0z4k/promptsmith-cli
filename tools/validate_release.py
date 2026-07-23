#!/usr/bin/env python3
"""Run the PromptSmith v1 release gate and record reproducible evidence.

This script intentionally uses the tools pinned by ``pyproject.toml``. It does
not install dependencies or modify source files. Run it from the repository
root inside a clean virtual environment with the ``dev`` and ``build`` extras
installed.
"""

from __future__ import annotations

import argparse
import json
import platform
import subprocess
import sys
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Sequence


@dataclass(frozen=True)
class CheckResult:
    name: str
    command: list[str]
    returncode: int
    duration_seconds: float

    @property
    def passed(self) -> bool:
        return self.returncode == 0


def run_check(name: str, command: Sequence[str], *, cwd: Path) -> CheckResult:
    print(f"\n==> {name}\n$ {' '.join(command)}", flush=True)
    started = time.monotonic()
    completed = subprocess.run(list(command), cwd=cwd, check=False)
    duration = round(time.monotonic() - started, 3)
    state = "PASS" if completed.returncode == 0 else "FAIL"
    print(f"[{state}] {name} ({duration:.3f}s)", flush=True)
    return CheckResult(name, list(command), completed.returncode, duration)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--report",
        type=Path,
        default=Path("release-validation.json"),
        help="JSON report destination (default: release-validation.json)",
    )
    parser.add_argument(
        "--keep-going",
        action="store_true",
        help="Run every check instead of stopping after the first failure",
    )
    args = parser.parse_args()

    root = Path(__file__).resolve().parents[1]
    pyproject = root / "pyproject.toml"
    if not pyproject.is_file():
        print("error: run from a PromptSmith source checkout", file=sys.stderr)
        return 2

    python = sys.executable
    checks: list[tuple[str, list[str]]] = [
        ("ruff", [python, "-m", "ruff", "check", "src"]),
        ("black", [python, "-m", "black", "--check", "src"]),
        ("isort", [python, "-m", "isort", "--check-only", "src"]),
        ("mypy", [python, "-m", "mypy", "src/promptsmith"]),
        ("pytest", [python, "-m", "pytest", "src/tests"]),
        ("build", [python, "-m", "build"]),
        ("twine", [python, "-m", "twine", "check", "dist/*"]),
    ]

    results: list[CheckResult] = []
    for name, command in checks:
        result = run_check(name, command, cwd=root)
        results.append(result)
        if not result.passed and not args.keep_going:
            break

    report = {
        "schema_version": 1,
        "candidate_commit": _git_commit(root),
        "python": sys.version,
        "platform": platform.platform(),
        "implementation": platform.python_implementation(),
        "results": [{**asdict(result), "passed": result.passed} for result in results],
        "passed": len(results) == len(checks) and all(result.passed for result in results),
    }
    destination = args.report if args.report.is_absolute() else root / args.report
    destination.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(f"\nValidation report: {destination}")

    if report["passed"]:
        print("Release gate passed for this interpreter and platform.")
        return 0
    print("Release gate did not pass. See the first failing command above.")
    return 1


def _git_commit(root: Path) -> str | None:
    try:
        completed = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=root,
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return None
    return completed.stdout.strip() or None


if __name__ == "__main__":
    raise SystemExit(main())
