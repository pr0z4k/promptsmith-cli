"""Print the project version from pyproject.toml and nothing else.

Used by build_cli.sh and build_windows.bat so both artifact names and the
frozen app's smoke test track the single source of truth automatically.
Works on Python 3.10 (regex fallback) and 3.11+ (tomllib).
"""

import re
import sys
from pathlib import Path

PYPROJECT = Path(__file__).resolve().parent.parent / "pyproject.toml"


def main() -> int:
    try:
        import tomllib

        with open(PYPROJECT, "rb") as f:
            print(tomllib.load(f)["project"]["version"])
        return 0
    except ModuleNotFoundError:
        pass
    text = PYPROJECT.read_text(encoding="utf-8")
    m = re.search(r'^version\s*=\s*"([^"]+)"', text, re.M)
    if not m:
        print("version not found in pyproject.toml", file=sys.stderr)
        return 1
    print(m.group(1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
