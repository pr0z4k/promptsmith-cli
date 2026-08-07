"""Shared pytest fixtures for the PromptSmith-cli test suite."""

import pytest

import promptsmith.cli.app as appmod


@pytest.fixture(autouse=True)
def _isolate_project_root(tmp_path, monkeypatch):
    """Redirect the app's project-root and config-path constants to tmp_path.

    `_PROJECT_ROOT` and `_CONFIG_PATH` in `promptsmith.cli.app` are
    module-level constants computed once at import time from `__file__`
    (`_CONFIG_PATH` is *not* re-derived from `_PROJECT_ROOT` at call time,
    so both must be patched independently). Left unpatched, any test that
    instantiates `PromptSmithApp()` reads and writes the real repository
    checkout's `config.yaml` (leaving a `config.yaml.bak` behind) and
    `exports/` directory instead of a sandboxed location - autouse here so
    no individual test has to remember to do this.

    Tests that intentionally need the real repository path (e.g. reading
    the actual `pyproject.toml` for a version-consistency check) should use
    their own local path constant rather than `appmod._PROJECT_ROOT`, as
    `test_version_and_about.py` already does.
    """
    monkeypatch.setattr(appmod, "_PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(appmod, "_CONFIG_PATH", tmp_path / "config.yaml")
