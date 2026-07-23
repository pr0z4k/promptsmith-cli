"""UI-level tests for PromptSmithApp, using Textual's headless test harness.

Focused on interaction-sequence bugs that unit tests on individual methods
can't catch - these require simulating real navigation while background
work is in flight. Uses asyncio.run() directly inside sync test functions
rather than pytest-asyncio, since that's not a project dependency.
"""
import asyncio
import time
from unittest.mock import patch

from promptsmith.cli.app import PromptSmithApp, SettingsScreen
from promptsmith.core.backends.llm_backend import LLMBasedBackend


FAKE_PROFILE = {
    "role": "Engineer",
    "domain": ["Eng"],
    "tone": "neutral",
    "format": "text",
    "constraints": [],
    "backend": "llm",
}


def slow_llm_refine(self, prompt, profile, polish_mode=False):
    time.sleep(1.2)
    return "A polished result, long enough to pass the length checks reliably in this test."


def test_settings_navigation_blocked_while_refine_in_progress():
    """Regression test: opening Settings (and therefore any modal reachable
    through it, like the LLM Run Log) while a background refine worker was
    actively updating reactive state caused rendering corruption - garbled,
    fragmented screen content, confirmed via real screenshots. Rather than
    try to make concurrent navigation safe, it's now blocked outright: the
    Settings button is disabled and action_settings() refuses to navigate
    while a refine is in progress, both verified here with a real
    simulated click, not just checking internal flags."""

    async def run():
        app = PromptSmithApp()
        async with app.run_test(size=(180, 50)) as pilot:
            await pilot.pause()
            with patch.object(app.profile_manager, "get_profile", return_value=FAKE_PROFILE):
                ta = app.query_one("#prompt_input")
                ta.load_text("a test prompt")

                with patch.object(LLMBasedBackend, "refine", slow_llm_refine):
                    app.action_refine()
                    await pilot.pause()

                    settings_button = app.query_one("#settings_button")
                    assert settings_button.disabled is True

                    await pilot.click("#settings_button")
                    await pilot.pause()
                    assert not isinstance(app.screen, SettingsScreen)

                    # Even a direct call (bypassing the button) must refuse.
                    app.action_settings()
                    await pilot.pause()
                    assert not isinstance(app.screen, SettingsScreen)

                    await asyncio.sleep(1.3)
                    await pilot.pause()

                    # Once the refine completes, navigation works again.
                    assert app.query_one("#settings_button").disabled is False
                    app.action_settings()
                    await pilot.pause()
                    assert isinstance(app.screen, SettingsScreen)

    asyncio.run(run())


def test_refining_animation_does_not_bleed_when_settings_opened_after_completion():
    """Sanity check for the normal case: once a refine has actually
    finished, Settings opens normally and its status bar reflects a real,
    completed status - not a stale or ticking 'Refining...' animation."""

    async def run():
        app = PromptSmithApp()
        async with app.run_test(size=(180, 50)) as pilot:
            await pilot.pause()
            with patch.object(app.profile_manager, "get_profile", return_value=FAKE_PROFILE):
                ta = app.query_one("#prompt_input")
                ta.load_text("a test prompt")

                with patch.object(LLMBasedBackend, "refine", slow_llm_refine):
                    app.action_refine()
                    await pilot.pause()
                    await asyncio.sleep(1.3)
                    await pilot.pause()

                    assert "Done" in app.status_message

                    app.action_settings()
                    await pilot.pause()
                    assert isinstance(app.screen, SettingsScreen)
                    status_text = str(app.screen.query_one("#status_bar").content)
                    assert "Refining" not in status_text

    asyncio.run(run())


def test_refined_output_reachable_on_small_terminal():
    """Regression test for a real reported bug: at common smaller terminal
    sizes (verified at 80x24, a very common default), the entire 'Refined
    Output' section - label and box - was silently clipped from the
    render, not just showing fewer visible rows. The underlying data was
    fine (Copy worked, confirming the widget's content was intact), but
    there was no way to actually see it, since #main_container was a
    plain Container with no overflow handling: content exceeding the
    terminal's height was just cut off, not made scrollable.

    Fixed by making #main_container a VerticalScroll, so the whole page
    scrolls when content doesn't fit. This test confirms the section is
    now reachable (max_scroll_y > 0, content present after scrolling to
    the end) rather than checking pixel-perfect visibility, since the
    real fix is reachability - some scrolling on a very small terminal is
    expected and fine; silently losing content forever is not."""

    async def run():
        app = PromptSmithApp()
        async with app.run_test(size=(80, 24)) as pilot:
            await pilot.pause()
            ta = app.query_one("#prompt_input")
            ta.load_text("Create a reusable React component for a card.")
            app.action_refine()
            await pilot.pause()
            await asyncio.sleep(0.3)
            await pilot.pause()

            main_container = app.query_one("#main_container")
            # The whole point of the fix: this must be scrollable, not 0.
            assert main_container.max_scroll_y > 0

            main_container.scroll_end(animate=False)
            await pilot.pause()

            refined_label = app.query_one("#refined_label")
            refined_output = app.query_one("#refined_prompt")
            # Both must actually be present in the widget tree with real
            # content - not removed, not empty - just previously unreachable.
            assert "Refined Output" in str(refined_label.content)
            assert len(str(refined_output.content)) > 0

    asyncio.run(run())


def test_large_terminal_unaffected_by_scroll_fix():
    """Sanity check: on a terminal large enough that everything already
    fits, the new VerticalScroll wrapper must be inert - no scrollbar, no
    behavior change from before the fix."""

    async def run():
        app = PromptSmithApp()
        async with app.run_test(size=(180, 50)) as pilot:
            await pilot.pause()
            ta = app.query_one("#prompt_input")
            ta.load_text("Create a reusable React component for a card.")
            app.action_refine()
            await pilot.pause()
            await asyncio.sleep(0.3)
            await pilot.pause()

            main_container = app.query_one("#main_container")
            assert main_container.max_scroll_y == 0

    asyncio.run(run())
