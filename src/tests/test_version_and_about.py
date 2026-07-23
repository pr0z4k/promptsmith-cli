"""Regression tests for version single-sourcing and the About screen.

The version must flow from pyproject.toml (via installed package
metadata) into __version__, the About modal, and --version output -
bumping pyproject.toml is the only step a release should need.
"""

import re
import subprocess
import sys
from pathlib import Path

import pytest

from promptsmith import (
    PRODUCT_NAME,
    PROJECT_URL,
    SUPPORT_URL,
    __version__,
    display_version,
)

_PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _pyproject_version() -> str:
    import tomllib

    with open(_PROJECT_ROOT / "pyproject.toml", "rb") as f:
        return tomllib.load(f)["project"]["version"]


def test_version_matches_pyproject():
    """__version__ must be the pyproject.toml value, read via metadata -
    a mismatch means the package wasn't reinstalled after a bump, or the
    single-source chain broke."""
    assert __version__ == _pyproject_version()


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("0.6.0b1", "0.6 Beta"),
        ("0.6b1", "0.6 Beta"),
        ("0.6.0", "0.6"),
        ("1.0.0", "1.0"),
        ("0.6.1b2", "0.6.1 Beta"),
        ("1.2.3rc1", "1.2.3 RC"),
        ("0.7.0a3", "0.7 Alpha"),
        ("1.0.0+local", "1.0"),
        ("not-a-version", "not-a-version"),
    ],
)
def test_display_version_formatting(raw, expected):
    assert display_version(raw) == expected


def test_product_identity_constants():
    assert PRODUCT_NAME == "PromptSmith-cli"
    assert PROJECT_URL == "https://codeberg.org/prozak/promptsmith-cli"
    assert SUPPORT_URL == "https://codeberg.org/prozak/promptsmith-cli/issues"
    assert SUPPORT_URL.startswith(PROJECT_URL)


def test_version_flag_prints_and_exits():
    """--version must print name + version and exit cleanly without
    starting the TUI - the build scripts' smoke test depends on this."""
    result = subprocess.run(
        [sys.executable, "-m", "promptsmith.cli.app", "--version"],
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert result.returncode == 0
    assert PRODUCT_NAME in result.stdout
    assert __version__ in result.stdout


def test_about_screen_contents_and_support_button(monkeypatch):
    """The About modal shows the product name, the pyproject-derived
    version, the project URL and license line, and Get Support opens the
    issue tracker."""
    import asyncio

    from textual.widgets import Label

    from promptsmith.cli.app import AboutScreen, PromptSmithApp

    opened = []
    import webbrowser

    monkeypatch.setattr(webbrowser, "open", lambda url: opened.append(url))

    async def run():
        app = PromptSmithApp()
        async with app.run_test(size=(120, 50)) as pilot:
            app.push_screen(AboutScreen())
            await pilot.pause()
            labels = [str(lbl.content) for lbl in app.screen.query(Label)]
            text = "\n".join(labels)
            assert PRODUCT_NAME in text
            assert f"Version {display_version()}" in text
            assert PROJECT_URL in text
            assert "MIT License" in text
            assert "2026" in text

            await pilot.click("#about_support")
            await pilot.pause()
            assert opened == [SUPPORT_URL]

            await pilot.click("#about_close")
            await pilot.pause()
            assert not isinstance(app.screen, AboutScreen)

    asyncio.run(run())


def test_no_orange_palette_remains():
    """The public build's visual cue is green-on-black; any orange hex
    creeping back into the TUI is a regression."""
    app_src = (_PROJECT_ROOT / "src" / "promptsmith" / "cli" / "app.py").read_text()
    for banned in ("#FF8C00", "#FFCC00", "#FFA500", "#806000"):
        assert banned.lower() not in app_src.lower()
    # And the green primaries are actually present.
    assert "#00CC33" in app_src
    assert "#66FF66" in app_src


def test_builtin_data_resolves_from_package():
    """Built-in profiles/templates ship inside the package so wheel
    installs work; the resolver must find them without a repo checkout."""
    from promptsmith.utils.path_utils import get_asset_path, get_builtin_data_dir

    data_dir = get_builtin_data_dir()
    assert (data_dir / "profiles").is_dir()
    assert (data_dir / "templates").is_dir()
    profiles = get_asset_path("profiles", __file__)
    assert profiles.is_dir()
    assert list(profiles.glob("*.yaml")), "no built-in profiles found"


def test_all_buttons_have_visible_labels():
    """Every Button must render a non-empty label with an explicit color
    span. Regression guard for the Textual 8 bug where bracketed labels
    like "[ Analyze ]" were parsed as markup and consumed, leaving empty
    buttons, and where CSS `color` didn't reach button text in terminals.
    """
    import asyncio

    from textual.widgets import Button

    from promptsmith.cli.app import PromptSmithApp

    async def run():
        app = PromptSmithApp()
        async with app.run_test(size=(160, 60)) as pilot:
            await pilot.pause()

            def check(screen_name):
                for b in app.screen.query(Button):
                    assert b.label.plain.strip(), (
                        f"{screen_name}: button {b.id!r} has an empty label - "
                        f"bracket markup was probably consumed"
                    )
                    assert b.label._spans, (
                        f"{screen_name}: button {b.id!r} label carries no "
                        f"color span - text will be invisible in a terminal"
                    )

            check("main")
            app.action_history()
            await pilot.pause()
            await pilot.pause()
            check("history")
            app.pop_screen()
            await pilot.pause()
            await pilot.click("#settings_button")
            await pilot.pause()
            check("settings")

    asyncio.run(run())


def test_command_palette_disabled():
    """The command palette is intentionally off: the app's colors are
    fixed hex literals, so Textual's theme switcher would do nothing
    visible and undermines the green-on-black identity."""
    from promptsmith.cli.app import PromptSmithApp

    assert PromptSmithApp.ENABLE_COMMAND_PALETTE is False


def test_wheel_install_asset_resolution_prefers_packaged(tmp_path, monkeypatch):
    """Regression for the second-launch profile-loss blocker: in a
    non-frozen install, get_asset_path must return the packaged data dir,
    NOT a same-named folder under the project root - even when that root
    folder exists (as it will once the user-data dir has been created).
    """
    import promptsmith.utils.path_utils as pu

    # Force non-frozen and point the "project root" at a temp dir that
    # ALSO contains a profiles/ folder (simulating ~/.promptsmith/profiles
    # having been created as the user-data dir on a prior launch).
    monkeypatch.setattr(pu, "is_frozen", lambda: False)
    fake_root = tmp_path / "userdata"
    (fake_root / "profiles").mkdir(parents=True)
    monkeypatch.setattr(pu, "get_project_root", lambda from_file=None: fake_root)

    resolved = pu.get_asset_path("profiles")
    packaged = pu.get_builtin_data_dir() / "profiles"

    # Must resolve to the packaged copy, not the (empty) root folder.
    assert resolved == packaged
    assert resolved != fake_root / "profiles"
    # And that packaged copy actually holds the built-ins.
    assert list(resolved.glob("*.yaml"))


def test_frozen_asset_resolution_prefers_sibling(tmp_path, monkeypatch):
    """The frozen path must still prefer a visible sibling folder next to
    the executable, so a portable build's editable profiles/ wins."""
    import promptsmith.utils.path_utils as pu

    monkeypatch.setattr(pu, "is_frozen", lambda: True)
    fake_root = tmp_path / "distroot"
    sibling = fake_root / "profiles"
    sibling.mkdir(parents=True)
    (sibling / "custom.yaml").write_text("name: custom\n")
    monkeypatch.setattr(pu, "get_project_root", lambda from_file=None: fake_root)

    resolved = pu.get_asset_path("profiles")
    assert resolved == sibling
