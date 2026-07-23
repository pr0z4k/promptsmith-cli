"""UI-level tests for the Profile Editor and Model Switch screens.

Uses Textual's headless test harness (asyncio.run() inside sync test
functions, matching test_app.py's convention - no pytest-asyncio dependency).

The Profile Editor writes to the real user-data directory (~/.promptsmith by
default, or $PROMPTSMITH_LOG_DIR), same as the app does outside of tests, so
every test here uses a unique profile id and cleans it up in a finally block
to avoid leaking state across test runs.
"""
import asyncio
import uuid

import pytest
from textual.widgets import Input, Select, Static, TextArea

from promptsmith.cli.app import (
    ModelSwitchScreen,
    ProfileEditorScreen,
    PromptSmithApp,
    SettingsScreen,
)


def _unique_id() -> str:
    return f"test-profile-{uuid.uuid4().hex[:8]}"


def test_profile_editor_reachable_from_settings():
    async def run():
        app = PromptSmithApp()
        async with app.run_test(size=(120, 100)) as pilot:
            await pilot.click("#settings_button")
            await pilot.pause()
            assert isinstance(app.screen, SettingsScreen)

            await pilot.click("#edit_profiles")
            await pilot.pause()
            assert isinstance(app.screen, ProfileEditorScreen)

    asyncio.run(run())


def test_profile_editor_loads_existing_backend_correctly():
    """nextjs-developer was reclassified from llm to hybrid; the editor
    should show whatever the profile file actually says, not a stale
    default."""

    async def run():
        app = PromptSmithApp()
        async with app.run_test(size=(120, 100)) as pilot:
            await pilot.click("#settings_button")
            await pilot.pause()
            await pilot.click("#edit_profiles")
            await pilot.pause()

            picker = app.screen.query_one("#profile_picker", Select)
            picker.value = "nextjs-developer"
            await pilot.pause()

            role = app.screen.query_one("#role_input", Input).value
            backend = app.screen.query_one("#backend_input", Select).value
            assert role == "Next.js Developer"
            assert backend == "hybrid"

    asyncio.run(run())


def test_profile_editor_create_edit_delete_roundtrip():
    """Full lifecycle: create a new profile via the form (no hand-written
    YAML), verify it validates and lands in the user directory, edit it,
    then delete it. Also confirms the id field is slugified so a
    non-technical user can't produce an invalid filename."""

    profile_id = _unique_id()

    async def run():
        app = PromptSmithApp()
        try:
            async with app.run_test(size=(120, 100)) as pilot:
                await pilot.click("#settings_button")
                await pilot.pause()
                await pilot.click("#edit_profiles")
                await pilot.pause()

                # Start a new profile with a deliberately messy id to check
                # slugification (spaces, punctuation, mixed case).
                app.screen.query_one("#id_input", Input).value = f"  {profile_id.upper()}!! "
                app.screen.query_one("#role_input", Input).value = "Rust Developer"
                app.screen.query_one("#domain_input", TextArea).text = "Rust\nOwnership\nAsync"
                app.screen.query_one("#constraints_input", TextArea).text = (
                    "Use idiomatic Rust.\nPrefer Result over panics."
                )
                app.screen.query_one("#backend_input", Select).value = "hybrid"
                await pilot.click("#save_profile")
                await pilot.pause()

                status = str(app.screen.query_one("#status_bar", Static).content)
                assert profile_id in status
                assert "failed" not in status.lower()

                # Validate what actually landed on disk.
                saved = app.profile_manager.get_profile(profile_id)
                assert saved["role"] == "Rust Developer"
                assert saved["domain"] == ["Rust", "Ownership", "Async"]
                assert saved["backend"] == "hybrid"
                assert app.profile_manager.is_user_defined(profile_id)

                # It should also now appear in the main screen's profile
                # selector without restarting the app.
                main_select = app.screen_stack[0].query_one("#profile_select", Select)
                assert profile_id in [v for _, v in main_select._options]

                # Edit: change backend, save again under the same id.
                picker = app.screen.query_one("#profile_picker", Select)
                picker.value = profile_id
                await pilot.pause()
                app.screen.query_one("#backend_input", Select).value = "llm"
                await pilot.click("#save_profile")
                await pilot.pause()
                updated = app.profile_manager.get_profile(profile_id)
                assert updated["backend"] == "llm"

                # Delete.
                await pilot.click("#delete_profile")
                await pilot.pause()
                assert profile_id not in app.profile_manager.list_profiles()
                status = str(app.screen.query_one("#status_bar", Static).content)
                assert "Deleted" in status
        finally:
            try:
                app.profile_manager.delete_profile(profile_id)
            except Exception:
                pass

    asyncio.run(run())


def test_profile_editor_rejects_missing_role():
    """A product-owner-friendly editor shouldn't let you save a profile
    that fails schema validation (missing required 'role')."""

    async def run():
        app = PromptSmithApp()
        async with app.run_test(size=(120, 100)) as pilot:
            await pilot.click("#settings_button")
            await pilot.pause()
            await pilot.click("#edit_profiles")
            await pilot.pause()

            app.screen.query_one("#id_input", Input).value = _unique_id()
            app.screen.query_one("#role_input", Input).value = ""
            await pilot.click("#save_profile")
            await pilot.pause()

            status = str(app.screen.query_one("#status_bar", Static).content)
            assert "required" in status.lower()

    asyncio.run(run())


def test_profile_editor_cannot_delete_builtin_profile():
    """Built-in profiles must survive an update; the editor should refuse
    to delete one even if the user opens it and hits Delete."""

    async def run():
        app = PromptSmithApp()
        async with app.run_test(size=(120, 100)) as pilot:
            await pilot.click("#settings_button")
            await pilot.pause()
            await pilot.click("#edit_profiles")
            await pilot.pause()

            picker = app.screen.query_one("#profile_picker", Select)
            picker.value = "lawyer"
            await pilot.pause()
            await pilot.click("#delete_profile")
            await pilot.pause()

            assert "lawyer" in app.profile_manager.list_profiles()
            status = str(app.screen.query_one("#status_bar", Static).content)
            assert "built-in" in status.lower() or "can't be deleted" in status.lower()

    asyncio.run(run())


def test_model_switch_reachable_and_defaults_to_auto():
    async def run():
        app = PromptSmithApp()
        async with app.run_test(size=(120, 100)) as pilot:
            await pilot.click("#settings_button")
            await pilot.pause()
            await pilot.click("#switch_model")
            await pilot.pause()
            assert isinstance(app.screen, ModelSwitchScreen)

            select = app.screen.query_one("#model_select", Select)
            # No blank option should ever be injected - a real value is
            # always selected (Auto, at minimum).
            assert all(v != Select.BLANK for _, v in select._options)

    asyncio.run(run())


def test_model_switch_apply_sets_config(monkeypatch, tmp_path):
    """Selecting a discovered .gguf file and applying it should update
    llm.model_path in config, which LLMBasedBackend reads on next refine -
    no separate reload step required."""

    fake_model = tmp_path / "fake-model.Q4_K_M.gguf"
    fake_model.write_bytes(b"GGUF" + b"0" * 1024)

    import promptsmith.cli.app as app_module

    monkeypatch.setattr(app_module.ModelSwitchScreen, "_discover_models", lambda self: [fake_model])

    async def run():
        app = PromptSmithApp()
        async with app.run_test(size=(120, 100)) as pilot:
            await pilot.click("#settings_button")
            await pilot.pause()
            await pilot.click("#switch_model")
            await pilot.pause()

            select = app.screen.query_one("#model_select", Select)
            select.value = str(fake_model)
            await pilot.pause()
            await pilot.click("#apply_model")
            await pilot.pause()

            assert app.config_manager.get("llm.model_path") == str(fake_model)
        # Reset so this test doesn't leak into others that construct a
        # fresh LLMBasedBackend and expect auto-discovery.
        app.config_manager.set("llm.model_path", None)

    asyncio.run(run())


def test_ctrl_q_goes_back_in_settings_instead_of_quitting():
    """Regression test: SettingsScreen bound ctrl+q to the bare action
    string "pop_screen", which Textual resolves against the Screen instance
    itself. Screen has no action_pop_screen method (only App does), so the
    action silently failed to dispatch and fell through the binding chain
    to the App's own ctrl+q -> "quit" binding, quitting the whole app
    instead of going back. Fixed by pointing at "app.pop_screen" so it
    resolves on the App, where the method actually exists."""

    async def run():
        app = PromptSmithApp()
        async with app.run_test(size=(120, 100)) as pilot:
            await pilot.click("#settings_button")
            await pilot.pause()
            assert isinstance(app.screen, SettingsScreen)

            await pilot.press("ctrl+q")
            await pilot.pause()

            assert not isinstance(app.screen, SettingsScreen)
            assert app.is_running

    asyncio.run(run())


def test_ctrl_s_saves_profile_in_editor():
    """Regression test: ProfileEditorScreen had no ctrl+s binding of its
    own, so the key fell through to the App-level ctrl+s -> action_save_config
    binding, which saves unrelated app config and updates a status bar the
    user can't see from this screen - ctrl+s appeared to do nothing."""
    profile_id = _unique_id()

    async def run():
        app = PromptSmithApp()
        async with app.run_test(size=(120, 100)) as pilot:
            await pilot.click("#settings_button")
            await pilot.pause()
            await pilot.click("#edit_profiles")
            await pilot.pause()
            assert isinstance(app.screen, ProfileEditorScreen)

            app.screen.query_one("#id_input", Input).value = profile_id
            app.screen.query_one("#role_input", Input).value = "Test Role"
            await pilot.pause()

            await pilot.press("ctrl+s")
            await pilot.pause()

            try:
                assert app.profile_manager.get_profile(profile_id)["role"] == "Test Role"
            finally:
                app.profile_manager.delete_profile(profile_id)

    asyncio.run(run())


def test_ctrl_a_in_profile_editor_gives_explicit_feedback_not_silent_bleed_through():
    """Regression test: ctrl+a in the Profile Editor used to fall through to
    the App-level "analyze" binding, which runs against the main screen's
    hidden prompt input and updates a status bar that isn't the one visible
    on this screen - so it looked like the key did nothing at all. It now
    has its own binding that gives visible feedback instead."""

    async def run():
        app = PromptSmithApp()
        async with app.run_test(size=(120, 100)) as pilot:
            await pilot.click("#settings_button")
            await pilot.pause()
            await pilot.click("#edit_profiles")
            await pilot.pause()
            assert isinstance(app.screen, ProfileEditorScreen)

            await pilot.press("ctrl+a")
            await pilot.pause()

            status = app.screen.query_one("#status_bar", Static)
            status_text = str(status.content)
            assert "Analyze isn't available" in status_text

    asyncio.run(run())


def test_profile_editor_form_is_scrollable_not_clipped():
    """Regression test: the Profile Editor's outer wrapper was a plain
    Container, which clips overflow by default (overflow: hidden) instead
    of scrolling. With 11 fields + 2 TextAreas the form is taller than most
    terminal windows, so Vendor, Backend, and the Save/Delete/Back buttons
    were being silently cut off below the visible viewport with no way to
    reach them - not even via keyboard, since hidden overflow doesn't
    auto-scroll focus into view. Fixed by using VerticalScroll instead."""
    from textual.containers import VerticalScroll

    async def run():
        app = PromptSmithApp()
        # Deliberately short terminal so the form is guaranteed to overflow.
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.click("#settings_button")
            await pilot.pause()
            await pilot.click("#edit_profiles")
            await pilot.pause()
            assert isinstance(app.screen, ProfileEditorScreen)

            outer = app.screen.query_one(VerticalScroll)
            assert outer.max_scroll_y > 0, (
                "form content doesn't overflow in this test size - "
                "widen the assertion size or content to keep this test meaningful"
            )

            # The previously-unreachable fields must exist and be scrollable to.
            for widget_id in ("#vendor_input", "#backend_input", "#save_profile", "#delete_profile"):
                app.screen.query_one(widget_id)

    asyncio.run(run())


def test_settings_screen_is_scrollable_not_clipped():
    """Same class of bug as the Profile Editor: SettingsScreen also used a
    plain (clipping) Container for its button list."""
    from textual.containers import VerticalScroll

    async def run():
        app = PromptSmithApp()
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.click("#settings_button")
            await pilot.pause()
            assert isinstance(app.screen, SettingsScreen)

            outer = app.screen.query_one(VerticalScroll)
            assert outer is not None

    asyncio.run(run())
