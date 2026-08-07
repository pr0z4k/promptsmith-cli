"""Verify one portable ZIP and write its SHA-256 sidecar.

This helper is intentionally platform-neutral so GitHub Actions uses the same
release-asset validation on macOS, Linux, and Windows.
"""

from __future__ import annotations

import hashlib
from pathlib import Path


def sha256_file(path: Path, chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(chunk_size), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> int:
    dist_dir = Path("dist")
    archives = sorted(dist_dir.glob("PromptSmith-cli-*.zip"))
    if len(archives) != 1:
        raise SystemExit(f"Expected exactly one portable ZIP, found: {archives}")

    archive = archives[0]
    if archive.stat().st_size == 0:
        raise SystemExit(f"Portable ZIP is empty: {archive}")

    checksum_path = archive.with_suffix(archive.suffix + ".sha256")
    digest = sha256_file(archive)
    checksum_path.write_text(f"{digest}  {archive.name}\n", encoding="utf-8")

    print(f"Verified portable artifact: {archive}")
    print(checksum_path.read_text(encoding="utf-8"), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
