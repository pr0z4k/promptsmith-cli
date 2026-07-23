"""Enforce PromptSmith's local-first network boundary."""

import ast
from pathlib import Path


NETWORK_MODULES = {
    "aiohttp",
    "http.client",
    "httpx",
    "requests",
    "socket",
    "urllib.request",
    "websockets",
}
ALLOWED_RUNTIME_FILES = {
    Path("scripts/package_models.py"),
}


def _network_imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names = [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom):
            names = [node.module or ""]
        else:
            continue
        for name in names:
            for network_module in NETWORK_MODULES:
                if name == network_module or name.startswith(network_module + "."):
                    found.add(name)
    return found


def test_runtime_network_access_is_confined_to_model_downloads():
    package_root = Path(__file__).resolve().parents[1] / "promptsmith"
    violations: dict[str, set[str]] = {}

    for source in package_root.rglob("*.py"):
        relative = source.relative_to(package_root)
        imports = _network_imports(source)
        if imports and relative not in ALLOWED_RUNTIME_FILES:
            violations[str(relative)] = imports

    assert not violations, (
        "Unexpected runtime networking outside the explicit model downloader: "
        f"{violations}. Update the security model deliberately before expanding "
        "PromptSmith's outbound network surface."
    )
