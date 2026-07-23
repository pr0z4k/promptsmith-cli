"""Static guardrails for PromptSmith's local-only runtime boundaries."""

import ast
from pathlib import Path


SOURCE_ROOT = Path(__file__).resolve().parents[1] / "promptsmith"
NETWORK_MODULES = {"requests", "httpx", "aiohttp", "http.client", "urllib.request"}
NETWORK_ALLOWLIST = {Path("scripts/package_models.py")}


def _python_files():
    return sorted(SOURCE_ROOT.rglob("*.py"))


def _relative(path: Path) -> Path:
    return path.relative_to(SOURCE_ROOT)


def test_outbound_network_code_is_confined_to_model_downloader():
    violations = []
    for path in _python_files():
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        imported = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module)

        outbound_imports = sorted(
            module
            for module in imported
            if module in NETWORK_MODULES
            or any(module.startswith(prefix + ".") for prefix in NETWORK_MODULES)
        )
        if outbound_imports and _relative(path) not in NETWORK_ALLOWLIST:
            violations.append(f"{_relative(path)}: {', '.join(outbound_imports)}")

    assert not violations, (
        "Unexpected outbound-network dependency outside the reviewed model downloader:\n"
        + "\n".join(violations)
    )


def test_runtime_has_no_subprocess_or_shell_execution_path():
    violations = []
    for path in _python_files():
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name == "subprocess":
                        violations.append(f"{_relative(path)} imports subprocess")
            elif isinstance(node, ast.ImportFrom) and node.module == "subprocess":
                violations.append(f"{_relative(path)} imports from subprocess")
            elif isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                if (
                    isinstance(node.func.value, ast.Name)
                    and node.func.value.id == "os"
                    and node.func.attr in {"system", "popen"}
                ):
                    violations.append(f"{_relative(path)} calls os.{node.func.attr}")

    assert not violations, (
        "A subprocess/shell execution path was added without security review:\n"
        + "\n".join(violations)
    )
