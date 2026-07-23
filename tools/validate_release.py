#!/usr/bin/env python3
"""Run the PromptSmith v1 release gate and record reproducible evidence.

Run this from the repository root inside a clean virtual environment with the
``dev`` and ``build`` extras installed. The script does not edit source files,
but it rebuilds ``dist/`` and creates a temporary virtual environment for the
wheel-install smoke test.
"""

from __future__ import annotations

import argparse
import json
import platform
import shutil
import subprocess
import sys
import tempfile
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
    printable = " ".join(str(part) for part in command)
    print(f"\n==> {name}\n$ {printable}", flush=True)
    started = time.monotonic()
    completed = subprocess.run([str(part) for part in command], cwd=cwd, check=False)
    duration = round(time.monotonic() - started, 3)
    state = "PASS" if completed.returncode == 0 else "FAIL"
    print(f"[{state}] {name} ({duration:.3f}s)", flush=True)
    return CheckResult(name, [str(part) for part in command], completed.returncode, duration)


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
        help="Run every independent check instead of stopping after the first failure",
    )
    args = parser.parse_args()

    root = Path(__file__).resolve().parents[1]
    if not (root / "pyproject.toml").is_file():
        print("error: run from a PromptSmith source checkout", file=sys.stderr)
        return 2

    python = sys.executable
    checks: list[tuple[str, list[str]]] = [
        ("ruff", [python, "-m", "ruff", "check", "src"]),
        ("black", [python, "-m", "black", "--check", "src"]),
        ("isort", [python, "-m", "isort", "--check-only", "src"]),
        ("mypy", [python, "-m", "mypy", "src/promptsmith"]),
        ("pytest", [python, "-m", "pytest", "src/tests"]),
    ]

    results: list[CheckResult] = []
    for name, command in checks:
        result = run_check(name, command, cwd=root)
        results.append(result)
        if not result.passed and not args.keep_going:
            return _finish(root, args.report, results, expected_checks=8)

    dist = root / "dist"
    if dist.exists():
        shutil.rmtree(dist)
    build_result = run_check("build", [python, "-m", "build"], cwd=root)
    results.append(build_result)
    if not build_result.passed:
        return _finish(root, args.report, results, expected_checks=8)

    artifacts = sorted(path for path in dist.iterdir() if path.is_file())
    if not artifacts:
        results.append(CheckResult("artifacts", [], 1, 0.0))
        print("[FAIL] build produced no files in dist/", flush=True)
        return _finish(root, args.report, results, expected_checks=8)

    twine_result = run_check(
        "twine",
        [python, "-m", "twine", "check", *[str(path) for path in artifacts]],
        cwd=root,
    )
    results.append(twine_result)
    if not twine_result.passed:
        return _finish(root, args.report, results, expected_checks=8)

    wheels = sorted(dist.glob("*.whl"))
    smoke_result = _wheel_smoke(root, wheels[0] if len(wheels) == 1 else None)
    results.append(smoke_result)
    return _finish(root, args.report, results, expected_checks=8)


def _wheel_smoke(root: Path, wheel: Path | None) -> CheckResult:
    if wheel is None:
        print("[FAIL] expected exactly one wheel in dist/", flush=True)
        return CheckResult("wheel-smoke", [], 1, 0.0)

    started = time.monotonic()
    commands: list[list[str]] = []
    returncode = 0
    with tempfile.TemporaryDirectory(prefix="promptsmith-release-") as temporary:
        venv = Path(temporary) / "venv"
        if platform.system() == "Windows":
            smoke_python = venv / "Scripts" / "python.exe"
        else:
            smoke_python = venv / "bin" / "python"

        commands = [
            [sys.executable, "-m", "venv", str(venv)],
            [str(smoke_python), "-m", "pip", "install", "--disable-pip-version-check", str(wheel)],
            [str(smoke_python), "-m", "promptsmith.cli.app", "--version"],
            [
                str(smoke_python),
                "-c",
                (
                    "from promptsmith.core.profiles import ProfileManager; "
                    "from promptsmith.utils.path_utils import get_asset_path; "
                    "p=get_asset_path('profiles', __file__); "
                    "assert len(ProfileManager(p).list_profiles()) > 0"
                ),
            ],
        ]
        for command in commands:
            completed = subprocess.run(command, cwd=root, check=False)
            if completed.returncode != 0:
                returncode = completed.returncode
                break

    duration = round(time.monotonic() - started, 3)
    state = "PASS" if returncode == 0 else "FAIL"
    print(f"[{state}] wheel-smoke ({duration:.3f}s)", flush=True)
    flattened = [" && ".join(" ".join(command) for command in commands)]
    return CheckResult("wheel-smoke", flattened, returncode, duration)


def _finish(root: Path, report_path: Path, results: list[CheckResult], *, expected_checks: int) -> int:
    passed = len(results) == expected_checks and all(result.passed for result in results)
    report = {
        "schema_version": 1,
        "candidate_commit": _git_commit(root),
        "python": sys.version,
        "platform": platform.platform(),
        "implementation": platform.python_implementation(),
        "results": [{**asdict(result), "passed": result.passed} for result in results],
        "passed": passed,
    }
    destination = report_path if report_path.is_absolute() else root / report_path
    destination.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(f"\nValidation report: {destination}")
    if passed:
        print("Release gate passed for this interpreter and platform.")
        return 0
    print("Release gate did not pass. See the failing command above.")
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
