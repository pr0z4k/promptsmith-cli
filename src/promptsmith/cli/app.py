"""
PromptSmith-cli Textual UI Application.

This module provides the main TUI application using the Textual framework.
"""

import logging
import os
import re
from pathlib import Path
from typing import Optional

from textual.app import App, ComposeResult
from textual.content import Content, Span
from textual.screen import Screen, ModalScreen
from textual.widgets import Input, Static, Button, Footer, Select, Label, TextArea, DataTable
from textual.binding import Binding
from textual.containers import Container, VerticalScroll
from textual.reactive import reactive
from textual import events, work

from promptsmith._version import PRODUCT_NAME, PROJECT_URL, SUPPORT_URL, __version__, display_version
from promptsmith.utils.path_utils import get_asset_path, get_project_root, get_user_data_dir

from promptsmith.core.runtime_model_fixes import configure_runtime_model_behavior
from promptsmith.scripts.model_catalog import configure_model_catalog

# Configure logging: write to a log file, never to the terminal.
# Textual takes exclusive control of the terminal (alternate screen buffer);
# a StreamHandler writing to stdout/stderr bypasses Textual's rendering
# entirely and corrupts the on-screen display as raw log lines get written
# straight onto the terminal, out of sync with what Textual thinks is there.
#
# Reuses get_user_data_dir() rather than an independent Path.home() default,
# so a frozen/portable build logs next to the executable (like profiles and
# templates) instead of a hidden home-directory location that diverges from
# where the app's other user-space files actually end up.
_LOG_DIR = get_user_data_dir()
_LOG_FILE = _LOG_DIR / "promptsmith.log"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler(_LOG_FILE, encoding="utf-8"),
    ]
)
logger = logging.getLogger(__name__)


def _is_blank_select_value(value: object) -> bool:
    """True when a Select delivered its no-selection sentinel.

    Textual 8 renamed the sentinel from Select.BLANK to Select.NULL (a
    NoSelection instance) and left BLANK behind as a plain False, so this
    checks both by identity and by the sentinel's type - Select emits a
    transient blank Changed event whenever set_options() rebuilds it.
    """
    null = getattr(Select, "NULL", None)
    blank = getattr(Select, "BLANK", None)
    if value is None or value is null or (blank is not None and value is blank):
        return True
    return null is not None and isinstance(value, type(null))

# Textual 8 button label workaround. Two problems are solved here:
#
# 1. Square brackets in a label (e.g. "[ Analyze ]") are parsed as
#    Textual content markup and silently consumed, leaving an EMPTY
#    button. This is why the buttons rendered blank after the Textual 8
#    upgrade.
# 2. The Button widget's CSS `color` no longer reliably reaches the
#    label text in ANSI terminal mode.
#
# Building a Content object explicitly (rather than passing a string
# that goes through markup parsing) fixes both: the literal text is
# preserved verbatim, and an explicit style span carries the color
# straight into the render output, independent of the CSS cascade.
_BUTTON_LABEL_COLOR = "#00CC33"
_BUTTON_LABEL_STYLE = f"bold {_BUTTON_LABEL_COLOR}"


def _styled_button(label: str, **kwargs) -> "Button":
    """Create a Button whose label renders verbatim in the app palette.

    Passes an explicit Content object so bracketed labels survive
    (markup parsing would eat them) and the color is baked into the
    text as a style span rather than relying on Button CSS `color`,
    which Textual 8 doesn't apply to label text in real terminals.
    """
    content = Content(label, spans=[Span(0, len(label), style=_BUTTON_LABEL_STYLE)])
    return Button(content, **kwargs)


logger.info(f"Logging to {_LOG_FILE}")

# Import core components
from promptsmith.core.refiner import PromptRefiner
from promptsmith.core.history import HistoryEntry, HistoryStore
from promptsmith.core.profiles import ProfileManager
from promptsmith.core.templates import TemplateManager
from promptsmith.core.config import ConfigManager
from promptsmith.core.prompt_analyzer import PromptAnalyzer, PromptAnalysis
from promptsmith.core.backends.rule_based import RuleBasedBackend
from promptsmith.core.backends.llm_backend import LLMBasedBackend
from promptsmith.core.plugins import BackendRegistry
from promptsmith.core.exceptions import (
    BackendError,
    ProfileNotFoundError,
    TemplateNotFoundError,
)

# Resolve paths relative to this file so the app works regardless of CWD
_PROJECT_ROOT = get_project_root(__file__)
_PROFILES_DIR = get_asset_path("profiles", __file__)
_TEMPLATES_DIR = get_asset_path("templates", __file__)
_CONFIG_PATH = _PROJECT_ROOT / "config.yaml"

# User-space profiles/templates - survive an update/reinstall, unlike
# anything a user adds directly to the bundled directories above, which
# get replaced wholesale the next time this is rebuilt or reinstalled.
_USER_PROFILES_DIR = get_user_data_dir() / "profiles"
_USER_TEMPLATES_DIR = get_user_data_dir() / "templates"

# Ensure required directories exist
os.makedirs(_PROFILES_DIR, exist_ok=True)
os.makedirs(_TEMPLATES_DIR, exist_ok=True)
os.makedirs(_CONFIG_PATH.parent, exist_ok=True)

# Register backends at module load time
try:
    BackendRegistry.register("rule", RuleBasedBackend)
    logger.info("Registered rule backend")
except Exception as e:
    logger.error(f"Failed to register rule backend: {e}")

try:
    BackendRegistry.register("llm", LLMBasedBackend)
    logger.info("Registered llm backend")
except Exception as e:
    logger.error(f"Failed to register llm backend: {e}")

try:
    from promptsmith.core.backends.hybrid_backend import HybridBackend
    BackendRegistry.register("hybrid", HybridBackend)
    logger.info("Registered hybrid backend")
except Exception as e:
    logger.error(f"Failed to register hybrid backend: {e}")


class PromptSmithApp(App):
    """PromptSmith-cli TUI - retro mainframe aesthetic."""

    # The green-on-black palette is the deliberate visual identity of the
    # public build (the internal build is orange) and every color in the
    # CSS is a fixed hex literal, not a theme token. Textual's built-in
    # command palette (Ctrl+P) offers a theme switcher, but since none of
    # this app's CSS references theme variables, switching a theme there
    # changes nothing visible - it's a broken-looking control for a
    # feature we intentionally don't want. Disabling it removes the dead
    # switcher and the "^p palette" footer hint in one line.
    ENABLE_COMMAND_PALETTE = False

    _prompt_input: TextArea
    _refined_output: Static
    _analysis_output: Static
    _profile_select: Select
    _template_select: Select
    
    profile_manager: ProfileManager
    template_manager: TemplateManager
    config_manager: ConfigManager
    refiner: PromptRefiner
    analyzer: PromptAnalyzer
    
    current_profile: str
    current_template: Optional[str]
    current_analysis: Optional[PromptAnalysis] = None

    CSS = """
    Screen {
        background: #000000;
        color: #00CC33;
    }
    #main_container {
        layout: vertical;
        width: 100%;
        height: 100%;
        border: double #00CC33;
        padding: 1 2;
    }
    #buttons {
        /* A grid (not a single horizontal row) so the seven action
           buttons wrap onto additional rows on narrow terminals instead
           of overflowing off-screen and becoming unclickable. Four per
           row keeps them reachable down to ~80 columns. */
        layout: grid;
        grid-size: 4;
        grid-gutter: 0 1;
        width: 1fr;
        height: auto;
        border: none;
        padding: 0;
    }
    #buttons Button {
        margin: 0 1 0 0;
    }
    Label#title {
        text-style: bold;
        color: #66FF66;
        dock: top;
        padding: 1 2;
    }
    Input {
        border: solid #00CC33;
        background: #000000;
        color: #00CC33;
        height: 3;
        padding: 0 1;
    }
    Input:focus { border: solid #66FF66; }
    TextArea#prompt_input {
        border: solid #00CC33;
        background: #000000;
        color: #00CC33;
        height: 6;
        padding: 0 1;
    }
    TextArea#prompt_input:focus {
        border: solid #66FF66;
    }
    #refined_prompt_scroll {
        border: solid #00CC33;
        height: 1fr;
        padding: 1 2;
    }
    Static#refined_prompt {
        color: #33FF33;
        width: 100%;
        height: auto;
    }
    Button {
        background: #000000;
        color: #00CC33;
        border: solid #00CC33;
        width: auto;
        padding: 0 2;
    }
    Button:focus { color: #66FF66; border: solid #66FF66; }
    Select {
        border: solid #00CC33;
        color: #00CC33;
        background: #000000;
        height: 3;
    }
    Select:focus { border: solid #66FF66; }
    SelectCurrent {
        background: #000000;
        color: #00CC33;
        border: none;
    }
    #profile_select:focus > SelectCurrent {
        border: none;
        background: #1a1a1a;
    }
    #profile_select.-expanded > SelectCurrent {
        border: none;
        background: #1a1a1a;
    }
    #template_select:focus > SelectCurrent {
        border: none;
        background: #1a1a1a;
    }
    #template_select.-expanded > SelectCurrent {
        border: none;
        background: #1a1a1a;
    }
    #profile_select SelectCurrent Static#label {
        color: #00CC33;
    }
    #template_select SelectCurrent Static#label {
        color: #00CC33;
    }
    #profile_select SelectCurrent.-has-value Static#label {
        color: #66FF66;
    }
    #template_select SelectCurrent.-has-value Static#label {
        color: #66FF66;
    }
    #profile_select SelectCurrent .arrow {
        color: #00CC33;
    }
    #template_select SelectCurrent .arrow {
        color: #00CC33;
    }
    SelectOverlay {
        background: #000000;
        color: #00CC33;
        border: solid #00CC33;
    }
    SelectOverlay > .option-list--option-highlighted {
        background: #00CC33;
        color: #000000;
    }
    Footer {
        background: #000000;
        color: #00CC33;
        dock: bottom;
        height: 1;
        padding: 0 1;
    }
    #status_bar {
        background: #000000;
        color: #66FF66;
        dock: bottom;
        width: 100%;
        height: 1;
        padding: 0 1;
    }
    #analysis_scroll {
        border: solid #00CC33;
        height: 12;
        padding: 0 1;
    }
    Static#analysis_output {
        color: #33FF33;
        width: 100%;
        height: auto;
    }
    Static#readiness_indicator {
        color: #00FF00;
        text-style: bold;
        width: auto;
        height: auto;
    }
    Static#readiness_indicator.not_ready {
        color: #FF0000;
    }
    #readiness_container {
        width: 100%;
        height: auto;
    }
    """
    
    BINDINGS = [
        Binding("ctrl+q", "quit", "Quit"),
        Binding("ctrl+enter", "analyze", "Analyze"),
        Binding("ctrl+r", "refine", "Refine"),
        Binding("ctrl+shift+a", "select_prompt_all", "Select Prompt"),
        Binding("ctrl+y", "copy", "Copy"),
        Binding("ctrl+s", "save_config", "Save Config"),
        Binding("down", "scroll_down", "Scroll Down"),
        Binding("up", "scroll_up", "Scroll Up"),
    ]

    status_message: reactive[str] = reactive("Ready", init=False)

    def __init__(self) -> None:
        super().__init__()
        
        try:
            self.profile_manager = ProfileManager(_PROFILES_DIR, user_dir=_USER_PROFILES_DIR)
            logger.info(f"Loaded {len(self.profile_manager.list_profiles())} profiles")
        except Exception as e:
            logger.error(f"Failed to initialize profile manager: {e}")
            self.profile_manager = ProfileManager(_PROFILES_DIR, user_dir=_USER_PROFILES_DIR)
            self.status_message = f"Warning: No profiles loaded"
        
        try:
            self.template_manager = TemplateManager(_TEMPLATES_DIR, user_dir=_USER_TEMPLATES_DIR)
            logger.info(f"Loaded {len(self.template_manager.list_templates())} templates")
        except Exception as e:
            logger.error(f"Failed to initialize template manager: {e}")
            self.template_manager = TemplateManager(_TEMPLATES_DIR, user_dir=_USER_TEMPLATES_DIR)
        
        try:
            self.config_manager = ConfigManager(_CONFIG_PATH)
            logger.info(f"Loaded configuration from {_CONFIG_PATH}")
        except Exception as e:
            logger.error(f"Failed to initialize config manager: {e}")
            self.config_manager = ConfigManager(_CONFIG_PATH)
        
        # Initialize analyzer
        try:
            self.analyzer = PromptAnalyzer()
            logger.info("Initialized prompt analyzer")
        except Exception as e:
            logger.error(f"Failed to initialize analyzer: {e}")
            self.status_message = f"Warning: Analyzer not available"
        
        self.current_profile = self.config_manager.get("default_profile", "general")
        self.current_template = self.config_manager.get("default_template", None)
        self.current_analysis = None
        
        try:
            self.refiner = PromptRefiner(
                self.profile_manager,
                self.template_manager,
            )
            logger.info("Initialized prompt refiner")
        except Exception as e:
            logger.error(f"Failed to initialize refiner: {e}")
            self.status_message = f"Error: {e}"

        # Prompt history (SQLite). Never fatal: if it can't open, the
        # feature disables itself and the rest of the app is unaffected.
        try:
            self.history = HistoryStore()
            if self.history.available:
                logger.info(f"History store ready ({self.history.count()} entries)")
            else:
                logger.warning("History store unavailable - history disabled")
        except Exception as e:
            logger.error(f"Failed to initialize history store: {e}")
            self.history = None

    def compose(self) -> ComposeResult:
        profile_options = [(p, p) for p in self.profile_manager.list_profiles()]
        if not profile_options:
            profile_options = [("general", "general")]
        
        template_options = [("None", "None")] + [
            (t, t) for t in self.template_manager.list_templates()
        ]
        
        self._valid_profile = (
            self.current_profile 
            if self.current_profile in [p for p, _ in profile_options] 
            else (profile_options[0][1] if profile_options else "general")
        )
        self._valid_template = (
            self.current_template 
            if self.current_template and self.current_template in [t for _, t in template_options] 
            else "None"
        )
        
        yield VerticalScroll(
            Label("┌─ PROMPTSMITH-CLI ─── Prompt Engineering Assistance ─┐", id="title"),
            Label("Enter your prompt below:"),
            TextArea(id="prompt_input"),
            Container(
                _styled_button("[ Analyze ]", id="analyze_button"),
                _styled_button("[ Refine ]", id="refine_button"),
                _styled_button("[ Copy ]", id="copy_button"),
                _styled_button("[ Clear ]", id="clear_button"),
                _styled_button("[ Export ]", id="export_button"),
                _styled_button("[ History ]", id="history_button"),
                _styled_button("[ Settings ]", id="settings_button"),
                id="buttons",
            ),
            Label("Select profile:"),
            Select(profile_options, id="profile_select", value=self._valid_profile),
            Label("Select template (optional):"),
            Select(template_options, id="template_select", value=self._valid_template),
            Label("Analysis:", id="analysis_label"),
            Container(
                Static(id="readiness_indicator"),
                id="readiness_container",
            ),
            VerticalScroll(
                Static(id="analysis_output"),
                id="analysis_scroll",
            ),
            Label("Refined Output:", id="refined_label"),
            VerticalScroll(
                Static(id="refined_prompt"),
                id="refined_prompt_scroll",
            ),
            Static("Ready", id="status_bar"),
            id="main_container",
        )
        yield Footer()

    def on_ready(self) -> None:
        try:
            self._prompt_input = self.query_one("#prompt_input", TextArea)
            self._refined_output = self.query_one("#refined_prompt", Static)
            self._analysis_output = self.query_one("#analysis_output", Static)
            self._profile_select = self.query_one("#profile_select", Select)
            self._template_select = self.query_one("#template_select", Select)
            self._readiness_indicator = self.query_one("#readiness_indicator", Static)
            self._init_select_values()
            
            profiles_count = len(self.profile_manager.list_profiles())
            templates_count = len(self.template_manager.list_templates())
            backend = self._get_profile_backend(self.current_profile)
            self.status_message = (
                f"Ready | {profiles_count} profiles | {templates_count} templates | "
                f"Profile: {self.current_profile} [{backend}]"
            )
            
            # Initialize analysis display
            self._update_analysis_display()
        except Exception as e:
            logger.error(f"Failed to initialize widgets: {e}")
            self.status_message = "Error: Widget initialization failed"

    def _init_select_values(self) -> None:
        profile_options = [
            opt[1] for opt in self._profile_select._options 
            if not _is_blank_select_value(opt[1])
        ]
        template_options = [
            opt[1] for opt in self._template_select._options 
            if not _is_blank_select_value(opt[1])
        ]
        
        if self._valid_profile in profile_options:
            self._profile_select.value = self._valid_profile
        elif profile_options:
            self._profile_select.value = profile_options[0]
            self.current_profile = profile_options[0]
            self.config_manager.set("default_profile", self.current_profile)
        
        if self._valid_template in template_options:
            self._template_select.value = self._valid_template
        elif template_options:
            self._template_select.value = "None"
            self.current_template = None
            self.config_manager.set("default_template", None)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        actions = {
            "analyze_button": self.action_analyze,
            "refine_button": self.action_refine,
            "copy_button": self.action_copy,
            "clear_button": self.action_clear,
            "export_button": self.action_export,
            "history_button": self.action_history,
            "settings_button": self.action_settings,
        }
        action_fn = actions.get(event.button.id)
        if action_fn:
            try:
                action_fn()
            except Exception as e:
                self.status_message = f"Error: {e}"
                logger.error(f"Button action failed: {e}")

    def on_select_changed(self, event: Select.Changed) -> None:
        try:
            # Ignore the transient blank blip Select emits while its
            # options are being replaced.
            if _is_blank_select_value(event.value):
                return
            if event.select.id == "profile_select":
                self.current_profile = event.value
                self.config_manager.set("default_profile", self.current_profile)
                backend = self._get_profile_backend(self.current_profile)
                self.status_message = f"Profile: {self.current_profile} [{backend}]"
            elif event.select.id == "template_select":
                self.current_template = None if event.value == "None" else event.value
                self.config_manager.set("default_template", self.current_template)
                self.status_message = f"Template: {self.current_template or 'None'}"
        except Exception as e:
            self.status_message = f"Error: {e}"

    def _get_profile_backend(self, profile_name: str) -> str:
        """Look up a profile's configured backend without running a refine."""
        try:
            profile = self.profile_manager.get_profile(profile_name)
            return profile.get("backend", "rule")
        except Exception:
            return "rule"

    def on_key(self, event: events.Key) -> None:
        if event.key == "down":
            self.action_scroll_down()
        elif event.key == "up":
            self.action_scroll_up()

    def watch_status_message(self, value: str) -> None:
        # Every screen (main, Settings, Profile Editor, Switch Model) has its
        # own local Static#status_bar for screen-specific messages. This
        # reactive only ever represents the *main* screen's status though -
        # target screen_stack[0] explicitly rather than self.query_one
        # (which searches whatever screen is currently topmost), or an
        # unrelated main-screen status change would silently overwrite a
        # pushed screen's own status text out from under it.
        try:
            self.screen_stack[0].query_one("#status_bar", Static).update(value)
        except Exception:
            logger.error(f"Failed to display status message: {value!r}")
    
    def _update_analysis_display(self) -> None:
        """Update the analysis display widgets based on current_analysis."""
        try:

            if self.current_analysis is None:
                self._analysis_output.update(
                    Content(
                        "Enter a prompt, then press Ctrl+Enter to analyze or Ctrl+R to refine. "
                        "Use Ctrl+Shift+A to select the whole prompt."
                    )
                )
                self._readiness_indicator.update("")
                self._readiness_indicator.remove_class("not_ready")
                return
            # Build analysis display text
            lines = []
            
            # Score and type
            score = self.current_analysis.get_readiness_percentage()
            lines.append(f"[bold]{self.current_analysis.detected_type.upper()}[/bold] | Score: [bold]{score}/100[/bold]")
            
            # Readiness indicator
            if self.current_analysis.is_ready:
                self._readiness_indicator.update("✓ READY FOR AI")
                self._readiness_indicator.remove_class("not_ready")
            else:
                self._readiness_indicator.update("✗ NEEDS WORK")
                self._readiness_indicator.add_class("not_ready")
            
            # Missing elements
            if self.current_analysis.missing:
                lines.append(f"[red]Missing:[/red] {', '.join(self.current_analysis.missing)}")
            
            # Smells
            if self.current_analysis.smells:
                smell_terms = [f"{s.term}({s.severity[0]})" for s in self.current_analysis.smells]
                lines.append(f"[yellow]Smells:[/yellow] {', '.join(smell_terms)}")
            
            # Recommended profile
            lines.append(f"[cyan]Suggested Profile:[/cyan] {self.current_analysis.recommended_profile}")
            
            # Recommendations
            if self.current_analysis.recommendations:
                # Show top 3 recommendations
                top_recs = self.current_analysis.recommendations[:3]
                rec_lines = []
                for rec in top_recs:
                    rec_lines.append(f"  - {rec.description}: {rec.action}")
                lines.append(f"[magenta]Recommendations:[/magenta]")
                lines.extend(rec_lines)

            # Challenges - informational clarifying questions, never blocking
            if self.current_analysis.challenges:
                top_challenges = self.current_analysis.challenges[:3]
                challenge_lines = [f"  ? {c.question}" for c in top_challenges]
                lines.append(f"[bold cyan]Worth clarifying:[/bold cyan]")
                lines.extend(challenge_lines)
            
            # Join with newlines for display
            display_text = "\n".join(lines)
            self._analysis_output.update(display_text)
            
        except Exception as e:
            logger.error(f"Failed to update analysis display: {e}")
            self._analysis_output.update(f"Analysis display error: {e}")

    def action_analyze(self) -> None:
        """Analyze the prompt without refining."""
        try:
            prompt = self._prompt_input.text.strip()
            if not prompt:
                self.status_message = "Error: no prompt entered."
                return
            
            self.status_message = "Analyzing..."
            
            # Perform analysis
            self.current_analysis = self.analyzer.analyze(
                prompt,
                self.current_profile if self.current_profile != "None" else None
            )
            
            # Update analysis display
            self._update_analysis_display()
            
            # Check if ready
            if self.current_analysis.is_ready:
                self.status_message = f"Analysis: READY ({self.current_analysis.score}/100)"
            else:
                self.status_message = f"Analysis: Needs work ({self.current_analysis.score}/100)"
                
        except Exception as e:
            self.status_message = f"Analysis Error: {e}"
            logger.exception("Unexpected error during analysis")
            self.current_analysis = None
            self._update_analysis_display()
    
    def action_refine(self) -> None:
        try:
            prompt = self._prompt_input.text.strip()
            if not prompt:
                self.status_message = "Error: no prompt entered."
                return

            # Analysis is fast and deterministic - fine to run synchronously.
            self.current_analysis = self.analyzer.analyze(
                prompt,
                self.current_profile if self.current_profile != "None" else None
            )
            self._update_analysis_display()

            backend = self._get_profile_backend(self.current_profile)
            self._set_refine_in_progress(True)
            self._start_refining_animation(backend)

            # The actual refine() call can block for a long time under an
            # LLM/hybrid backend - run it off the UI thread so status updates
            # actually get a chance to paint, and the app stays responsive.
            self._refine_worker(prompt)

        except ProfileNotFoundError as e:
            self._set_refine_in_progress(False)
            self.status_message = f"Error: Profile not found - {e}"
        except TemplateNotFoundError as e:
            self._set_refine_in_progress(False)
            self.status_message = f"Error: Template not found - {e}"
        except BackendError as e:
            self._set_refine_in_progress(False)
            self.status_message = f"Error: Backend error - {e}"
        except Exception as e:
            self._set_refine_in_progress(False)
            self.status_message = f"Error: {e}"
            logger.exception("Unexpected error during refinement")

    def _set_refine_in_progress(self, in_progress: bool) -> None:
        """Track whether a refine is actively running, and disable
        navigation to Settings while it is. Opening Settings (or any modal
        reachable through it, like the LLM Run Log) while a background
        refine worker is actively updating reactive state has caused
        rendering corruption - eliminating the concurrent scenario entirely
        is far more reliable than trying to make it safe."""
        self._refine_in_progress = in_progress
        try:
            settings_button = self.query_one("#settings_button", Button)
            settings_button.disabled = in_progress
        except Exception:
            pass

    def _start_refining_animation(self, backend: str) -> None:
        """Start a ticking status animation for the duration of a refine.
        Guarantees at least one visible status update even if the actual
        work finishes very quickly (e.g. the model is already warm) - a
        single fixed message set once can otherwise be overwritten by the
        final status before a human eye ever registers it."""
        self._stop_refining_animation()
        self._refining_backend = backend
        self._refining_dot_cycle = 0
        self._refining_total_ticks = 0
        label = f"Refining with {backend} backend" if backend in ("llm", "hybrid") else "Refining"
        self.status_message = f"{label}..."
        self._refining_timer = self.set_interval(0.4, self._tick_refining_animation)

    def _tick_refining_animation(self) -> None:
        try:
            if len(self.screen_stack) != 1:
                # A modal or Settings has been pushed on top since the refine
                # started - don't force this animation's status text onto a
                # screen it was never meant for. It'll resume naturally once
                # back on the main screen, since the timer keeps running.
                return
            self._refining_dot_cycle = (self._refining_dot_cycle % 3) + 1
            self._refining_total_ticks += 1
            dots = "." * self._refining_dot_cycle
            label = (
                f"Refining with {self._refining_backend} backend"
                if self._refining_backend in ("llm", "hybrid") else "Refining"
            )
            elapsed = self._refining_total_ticks * 0.4
            self.status_message = f"{label}{dots} (elapsed: {elapsed:.0f}s+)"
        except Exception as e:
            # A timer callback runs on its own schedule, independent of the
            # refine it's animating for - it must never be able to crash or
            # destabilize the app. Stop cleanly rather than keep firing into
            # a possibly broken state.
            logger.debug(f"Refining animation tick failed, stopping timer: {e}")
            self._stop_refining_animation()

    def _stop_refining_animation(self) -> None:
        timer = getattr(self, "_refining_timer", None)
        if timer is not None:
            timer.stop()
            self._refining_timer = None

    @work(thread=True, exclusive=True, group="refine")
    def _refine_worker(self, prompt: str) -> None:
        try:
            refined = self.refiner.refine(
                prompt,
                profile_name=self.current_profile,
                template_name=self.current_template,
            )

            warning = getattr(self.refiner, "last_warning", None)
            backend_used = getattr(self.refiner, "last_backend_used", None)
            model_used = getattr(self.refiner, "last_model_used", None)
            if backend_used in ("llm", "hybrid") and model_used:
                backend_tag = f"[{backend_used}: {model_used}]"
            elif backend_used:
                backend_tag = f"[{backend_used}]"
            else:
                backend_tag = ""

            if self.current_analysis.is_ready:
                status = (
                    f"READY | Done (warning: {warning}) {backend_tag}" if warning
                    else f"READY | Done. {backend_tag}"
                )
            else:
                status = (
                    f"Needs work | Done (warning: {warning}) {backend_tag}" if warning
                    else f"Needs work | Done. {backend_tag}"
                )

            self.call_from_thread(self._apply_refine_result, refined, status)
        except ProfileNotFoundError as e:
            self.call_from_thread(self._finish_refine_with_error, f"Error: Profile not found - {e}")
        except TemplateNotFoundError as e:
            self.call_from_thread(self._finish_refine_with_error, f"Error: Template not found - {e}")
        except BackendError as e:
            self.call_from_thread(self._finish_refine_with_error, f"Error: Backend error - {e}")
        except Exception as e:
            logger.exception("Unexpected error during refinement")
            self.call_from_thread(self._finish_refine_with_error, f"Error: {e}")

    def _apply_refine_result(self, refined: str, status: str) -> None:
        self._stop_refining_animation()
        self._set_refine_in_progress(False)
        self._refined_output.update(refined)
        if len(self.screen_stack) == 1:
            self.status_message = status
        self._record_history(refined)

    def _record_history(self, refined: str) -> None:
        """Persist this refine to local history. Best-effort: a history
        failure must never disturb the refine the user just completed, so
        everything here is guarded and silent beyond a log line."""
        history = getattr(self, "history", None)
        if history is None or not getattr(history, "available", False):
            return
        try:
            prompt = self._prompt_input.text.strip()
            if not prompt or not refined.strip():
                return
            entry = HistoryEntry(
                prompt=prompt,
                refined=refined,
                profile=self.current_profile,
                template=self.current_template,
                backend=getattr(self.refiner, "last_backend_used", None),
                model=getattr(self.refiner, "last_model_used", None),
                analysis=HistoryEntry.analysis_from_object(self.current_analysis),
            )
            history.add(entry)
        except Exception as exc:
            logger.error(f"Could not record history entry: {exc}")

    def _finish_refine_with_error(self, status: str) -> None:
        self._stop_refining_animation()
        self._set_refine_in_progress(False)
        if len(self.screen_stack) == 1:
            self.status_message = status

    def action_copy(self) -> None:
        try:
            renderable = self._refined_output.content
            plain = getattr(renderable, "plain", str(renderable))
            if not plain.strip():
                self.status_message = "Nothing to copy."
                return
            
            try:
                import pyperclip
                pyperclip.copy(plain)
                self.status_message = "Copied to clipboard."
            except ImportError:
                self.status_message = "pyperclip not installed - pip install pyperclip"
            except Exception as exc:
                self.status_message = f"Copy failed: {exc}"
        except Exception as e:
            self.status_message = f"Error: {e}"

    def action_clear(self) -> None:
        try:
            self._prompt_input.clear()
            self._refined_output.update("")
            self.current_analysis = None
            self._update_analysis_display()
            self.status_message = "Cleared."
        except Exception as e:
            self.status_message = f"Error: {e}"

    def action_export(self) -> None:
        try:
            from datetime import datetime
            prompt = self._prompt_input.text.strip()
            renderable = self._refined_output.content
            refined = getattr(renderable, "plain", str(renderable)).strip()

            if not prompt and not refined:
                self.status_message = "Nothing to export yet - enter a prompt first."
                return

            exports_dir = _PROJECT_ROOT / "exports"
            exports_dir.mkdir(parents=True, exist_ok=True)
            timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
            export_path = exports_dir / f"PromptSmith-cli-Session-{timestamp}.md"

            lines = [
                "# PromptSmith-cli Session Export",
                f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
                "",
                f"**Profile:** {self.current_profile or '(none)'}",
                f"**Template:** {self.current_template or '(none)'}",
                "",
                "## Original Prompt",
                prompt or "*(empty)*",
                "",
                "## Refined Output",
                refined or "*(not yet refined)*",
            ]
            export_path.write_text("\n".join(lines), encoding="utf-8")
            self.status_message = f"Session exported -> {export_path}"
        except Exception as exc:
            self.status_message = f"Export failed: {exc}"

    def action_save_config(self) -> None:
        try:
            self.config_manager.save()
            self.status_message = "Config saved."
        except Exception as e:
            self.status_message = f"Error saving config: {e}"

    def action_scroll_down(self) -> None:
        try:
            self.query_one("#refined_prompt_scroll", VerticalScroll).scroll_down()
        except Exception:
            pass

    def action_scroll_up(self) -> None:
        try:
            self.query_one("#refined_prompt_scroll", VerticalScroll).scroll_up()
        except Exception:
            pass

    def refresh_profile_options(self) -> None:
        """Reload profiles from disk and rebuild the main screen's profile
        Select widget in place - called after the profile editor saves,
        renames, or deletes a profile so the main screen reflects it
        immediately without needing an app restart.

        Uses screen_stack[0] (the base screen) rather than self.query_one,
        since this is always called from a screen pushed on top (Settings ->
        Profile Editor) - App.query_one only searches the currently active
        top screen and would silently find nothing otherwise."""
        try:
            self.profile_manager.reload()
            options = [(p, p) for p in self.profile_manager.list_profiles()]
            if not options:
                options = [("general", "general")]
            base_screen = self.screen_stack[0]
            select = base_screen.query_one("#profile_select", Select)
            select.set_options(options)
            valid_names = [p for _, p in options]
            if self.current_profile not in valid_names:
                self.current_profile = valid_names[0]
                self.config_manager.set("default_profile", self.current_profile)
            select.value = self.current_profile
        except Exception as e:
            logger.error(f"Failed to refresh profile list: {e}")

    def action_select_prompt_all(self) -> None:
        """Select the complete prompt without relying on terminal Cmd+A."""

        self._prompt_input.focus()
        select_all = getattr(self._prompt_input, "action_select_all", None)

        if callable(select_all):
            select_all()
            self.status_message = "Prompt selected."
        else:
            self.status_message = "Select All is unavailable in this Textual version."

    def action_history(self) -> None:
        if getattr(self, "_refine_in_progress", False):
            self.status_message = "Please wait for the current refine to finish."
            return
        history = getattr(self, "history", None)
        if history is None or not getattr(history, "available", False):
            self.status_message = "History is unavailable (database could not be opened)."
            return
        try:
            self.push_screen(HistoryScreen(self))
        except Exception as e:
            self.status_message = f"Error opening history: {e}"

    def action_settings(self) -> None:
        if getattr(self, "_refine_in_progress", False):
            self.status_message = "Please wait for the current refine to finish before opening Settings."
            return
        try:
            self.push_screen(SettingsScreen(self))
        except Exception as e:
            self.status_message = f"Error opening settings: {e}"

    @work(thread=True, exclusive=True, group="model_download")
    def start_model_download(self) -> None:
        def on_progress(model_key: str, downloaded: int, total: int) -> None:
            downloaded_mb = downloaded / (1024 * 1024)
            if total > 0:
                pct = min(100, int(downloaded * 100 / total))
                total_mb = total / (1024 * 1024)
                text = f"Downloading {model_key}... {pct}% ({downloaded_mb:.1f}/{total_mb:.1f} MB)"
            else:
                text = f"Downloading {model_key}... {downloaded_mb:.1f} MB"
            self.call_from_thread(setattr, self, "status_message", text)

        try:
            from promptsmith.scripts.package_models import main as download_models
            results = download_models(progress_callback=on_progress)
            failed = {key: r["error"] for key, r in results.items() if not r["success"]}
            if failed:
                # Surface the actual reason for the FIRST failure directly,
                # rather than a generic "check logs" - especially important
                # for something like the HuggingFace Xet CAS-bridge issue,
                # where the specific explanation is genuinely actionable and
                # shouldn't be buried somewhere the user has to go looking.
                first_key, first_error = next(iter(failed.items()))
                if len(failed) == 1:
                    message = f"{first_key} failed: {first_error}"
                else:
                    message = f"{len(failed)} downloads failed. {first_key}: {first_error}"
            elif results:
                message = "Model download complete. Check models/ directory."
            else:
                message = "No models configured to download."
        except Exception as exc:
            message = f"Model download failed: {exc}"
        self.call_from_thread(setattr, self, "status_message", message)

    @work(thread=True, exclusive=True, group="model_download")
    def start_custom_model_download(self, url: str) -> None:
        def on_progress(label: str, downloaded: int, total: int) -> None:
            downloaded_mb = downloaded / (1024 * 1024)
            if total > 0:
                pct = min(100, int(downloaded * 100 / total))
                total_mb = total / (1024 * 1024)
                text = f"Downloading {label}... {pct}% ({downloaded_mb:.1f}/{total_mb:.1f} MB)"
            else:
                text = f"Downloading {label}... {downloaded_mb:.1f} MB"
            self.call_from_thread(setattr, self, "status_message", text)

        try:
            from promptsmith.scripts.package_models import download_custom_model
            dest_path = download_custom_model(url, progress_callback=on_progress)
            message = f"Downloaded -> {dest_path}"
        except Exception as exc:
            message = f"Custom download failed: {exc}"
        self.call_from_thread(setattr, self, "status_message", message)


class AboutScreen(ModalScreen):
    """A dismissible overlay popup showing app info."""

    CSS = """
    AboutScreen {
        align: center middle;
    }
    #about_dialog {
        width: 60;
        height: auto;
        border: double #00CC33;
        background: #000000;
        padding: 1 2;
    }
    #about_dialog Label {
        width: 100%;
        content-align: center middle;
        color: #00CC33;
    }
    #about_title {
        text-style: bold;
        color: #66FF66;
    }
    Button#about_support, Button#about_close {
        width: 100%;
        margin-top: 1;
        background: #000000;
        color: #00CC33;
        border: solid #00CC33;
    }
    Button#about_support:focus, Button#about_close:focus {
        color: #66FF66;
        border: solid #66FF66;
    }
    """

    BINDINGS = [
        Binding("escape", "dismiss", "Close"),
    ]

    def compose(self) -> ComposeResult:
        yield Container(
            Label(f"{PRODUCT_NAME}", id="about_title"),
            Label(f"Version {display_version()}"),
            Label(""),
            Label("Visit us at"),
            Label(PROJECT_URL),
            Label(""),
            Label("2026 - MIT License"),
            _styled_button("[ Get Support ]", id="about_support"),
            _styled_button("[ Close ]", id="about_close"),
            id="about_dialog",
        )

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "about_close":
            self.dismiss()
        elif event.button.id == "about_support":
            import webbrowser

            try:
                webbrowser.open(SUPPORT_URL)
            except Exception:
                # Headless terminals / SSH sessions may have no browser -
                # the URL is already visible on screen either way.
                pass


class HistoryScreen(ModalScreen):
    """Prompt history browser.

    Shows recorded refines in a selectable grid, with a preview of the
    highlighted entry and actions to copy its refined output, delete it,
    export the whole history (JSON + CSV), or clear everything.
    """

    CSS = """
    HistoryScreen {
        align: center middle;
    }
    #history_dialog {
        width: 90%;
        height: 90%;
        border: double #00CC33;
        background: #000000;
        padding: 1 2;
    }
    #history_title {
        text-style: bold;
        color: #66FF66;
        width: 100%;
        content-align: center middle;
    }
    #history_table {
        height: 1fr;
        border: solid #00CC33;
        background: #000000;
        color: #00CC33;
    }
    #history_table > .datatable--header {
        background: #000000;
        color: #66FF66;
        text-style: bold;
    }
    #history_table > .datatable--cursor {
        background: #1E661E;
        color: #66FF66;
    }
    #history_preview_label {
        color: #66FF66;
        text-style: bold;
        margin-top: 1;
    }
    #history_preview_scroll {
        height: 8;
        border: solid #00CC33;
        background: #000000;
    }
    #history_preview {
        color: #00CC33;
        width: 100%;
        height: auto;
        padding: 0 1;
    }
    #history_button_row {
        layout: horizontal;
        height: auto;
        padding-top: 1;
        align: center middle;
    }
    #history_button_row Button {
        margin: 0 1 0 0;
        width: auto;
        padding: 0 1;
        background: #000000;
        color: #00CC33;
        border: solid #00CC33;
    }
    #history_button_row Button:focus {
        color: #66FF66;
        border: solid #66FF66;
    }
    #history_status {
        color: #00CC33;
        width: 100%;
        content-align: center middle;
        margin-top: 1;
    }
    """

    BINDINGS = [
        Binding("escape", "dismiss", "Close"),
    ]

    def __init__(self, main_app: "PromptSmithApp") -> None:
        super().__init__()
        self.main_app = main_app
        self.history = main_app.history
        self._entries: list = []
        self._id_by_row_index: list = []
        # Clear All is destructive and irreversible, so it's armed on the
        # first press and only executes on a second confirming press. Any
        # other action (or reopening the modal) disarms it.
        self._clear_armed = False

    def compose(self) -> ComposeResult:
        yield Container(
            Label("Prompt History", id="history_title"),
            DataTable(id="history_table", cursor_type="row", zebra_stripes=True),
            Label("Selected entry:", id="history_preview_label"),
            VerticalScroll(
                Static(id="history_preview"),
                id="history_preview_scroll",
            ),
            Container(
                _styled_button("[ Copy Refined ]", id="history_copy"),
                _styled_button("[ Delete ]", id="history_delete"),
                _styled_button("[ Export JSON ]", id="history_export_json"),
                _styled_button("[ Export CSV ]", id="history_export_csv"),
                _styled_button("[ Clear All ]", id="history_clear"),
                _styled_button("[ Close ]", id="history_close"),
                id="history_button_row",
            ),
            Static("", id="history_status"),
            id="history_dialog",
        )

    def on_mount(self) -> None:
        table = self.query_one("#history_table", DataTable)
        table.add_column("When", key="when", width=19)
        table.add_column("Profile", key="profile", width=18)
        table.add_column("Backend", key="backend", width=10)
        table.add_column("Score", key="score", width=6)
        table.add_column("Prompt", key="prompt")
        self._reload()

    def _reload(self) -> None:
        """Refresh the grid from the store and update the preview."""
        table = self.query_one("#history_table", DataTable)
        table.clear()
        self._entries = self.history.list()
        self._id_by_row_index = []
        for e in self._entries:
            when = self._format_ts(e.created_at)
            score = ""
            if isinstance(e.analysis, dict) and e.analysis.get("score") is not None:
                score = str(e.analysis.get("score"))
            prompt_preview = e.prompt.replace("\n", " ")
            if len(prompt_preview) > 80:
                prompt_preview = prompt_preview[:77] + "..."
            table.add_row(
                when,
                e.profile or "None",
                e.backend or "-",
                score,
                prompt_preview,
            )
            self._id_by_row_index.append(e.id)
        self._set_status(f"{len(self._entries)} " + ("entry" if len(self._entries) == 1 else "entries"))
        self._update_preview()

    @staticmethod
    def _format_ts(iso: str) -> str:
        """Render the stored UTC ISO timestamp as local 'YYYY-MM-DD HH:MM'."""
        if not iso:
            return ""
        try:
            from datetime import datetime

            dt = datetime.fromisoformat(iso)
            return dt.astimezone().strftime("%Y-%m-%d %H:%M:%S")
        except Exception:
            return iso[:19]

    def _current_entry(self):
        table = self.query_one("#history_table", DataTable)
        idx = table.cursor_row
        if idx is None or idx < 0 or idx >= len(self._entries):
            return None
        return self._entries[idx]

    def _update_preview(self) -> None:
        preview = self.query_one("#history_preview", Static)
        entry = self._current_entry()
        if entry is None:
            preview.update("(no entry selected)")
            return
        a = entry.analysis if isinstance(entry.analysis, dict) else {}
        lines = []
        lines.append(f"[bold]Prompt:[/bold] {entry.prompt}")
        lines.append("")
        lines.append(f"[bold]Refined:[/bold] {entry.refined}")
        if a:
            lines.append("")
            meta = []
            if a.get("detected_type"):
                meta.append(f"type={a['detected_type']}")
            if a.get("score") is not None:
                meta.append(f"score={a['score']}")
            if a.get("is_ready") is not None:
                meta.append(f"ready={a['is_ready']}")
            if meta:
                lines.append(f"[bold]Analysis:[/bold] {', '.join(meta)}")
            if a.get("missing"):
                lines.append(f"[bold]Missing:[/bold] {', '.join(a['missing'])}")
            if a.get("recommendations"):
                lines.append(f"[bold]Recommendations:[/bold] {len(a['recommendations'])}")
        preview.update("\n".join(lines))

    def on_data_table_row_highlighted(self, event) -> None:
        self._update_preview()

    def _set_status(self, msg: str) -> None:
        try:
            self.query_one("#history_status", Static).update(msg)
        except Exception:
            pass

    def on_button_pressed(self, event: Button.Pressed) -> None:
        bid = event.button.id
        # Any action other than a second Clear press cancels a pending
        # clear confirmation.
        if bid != "history_clear" and self._clear_armed:
            self._disarm_clear()
        if bid == "history_close":
            self.dismiss()
        elif bid == "history_copy":
            self._copy_selected()
        elif bid == "history_delete":
            self._delete_selected()
        elif bid == "history_export_json":
            self._export("json")
        elif bid == "history_export_csv":
            self._export("csv")
        elif bid == "history_clear":
            self._clear_all()

    def _copy_selected(self) -> None:
        entry = self._current_entry()
        if entry is None:
            self._set_status("Nothing selected to copy.")
            return
        try:
            import pyperclip

            pyperclip.copy(entry.refined)
            self._set_status("Refined prompt copied to clipboard.")
        except ImportError:
            self._set_status("pyperclip not installed - cannot copy.")
        except Exception as exc:
            self._set_status(f"Copy failed: {exc}")

    def _delete_selected(self) -> None:
        entry = self._current_entry()
        if entry is None:
            self._set_status("Nothing selected to delete.")
            return
        if self.history.delete(entry.id):
            self._reload()
            self._set_status("Entry deleted.")
        else:
            self._set_status("Delete failed.")

    def _clear_button(self):
        try:
            return self.query_one("#history_clear", Button)
        except Exception:
            return None

    def _disarm_clear(self) -> None:
        self._clear_armed = False
        btn = self._clear_button()
        if btn is not None:
            btn.label = Content(
                "[ Clear All ]",
                spans=[Span(0, len("[ Clear All ]"), style=_BUTTON_LABEL_STYLE)],
            )

    def _clear_all(self) -> None:
        count = self.history.count()
        if count == 0:
            self._set_status("History is already empty.")
            return
        if not self._clear_armed:
            # First press: arm and warn. Nothing is deleted yet.
            self._clear_armed = True
            btn = self._clear_button()
            if btn is not None:
                warn = "[ Confirm Clear? ]"
                btn.label = Content(
                    warn, spans=[Span(0, len(warn), style="bold #66FF66")]
                )
            self._set_status(
                f"This permanently deletes all {count} "
                + ("entry" if count == 1 else "entries")
                + ". Press Clear All again to confirm, or any other button to cancel."
            )
            return
        # Second press: execute.
        removed = self.history.clear()
        self._disarm_clear()
        self._reload()
        self._set_status(f"Cleared {removed} " + ("entry." if removed == 1 else "entries."))

    def _export(self, fmt: str) -> None:
        try:
            from datetime import datetime

            exports_dir = _PROJECT_ROOT / "exports"
            exports_dir.mkdir(parents=True, exist_ok=True)
            timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
            if fmt == "json":
                out = exports_dir / f"PromptSmith-cli-History-{timestamp}.json"
                n = self.history.export_json(out)
            else:
                out = exports_dir / f"PromptSmith-cli-History-{timestamp}.csv"
                n = self.history.export_csv(out)
            self._set_status(f"Exported {n} entries -> {out.name}")
        except Exception as exc:
            self._set_status(f"Export failed: {exc}")


class SettingsScreen(Screen):
    CSS = """
    Screen {
        background: #000000;
        color: #00CC33;
    }
    Container, VerticalScroll {
        layout: vertical;
        width: 100%;
        height: 100%;
        border: double #00CC33;
        padding: 1 2;
    }
    Label#title {
        text-style: bold;
        color: #66FF66;
        dock: top;
        padding: 1 2;
    }
    Button {
        background: #000000;
        color: #00CC33;
        border: solid #00CC33;
        width: 100%;
        padding: 0 2;
        margin: 0 0 1 0;
    }
    Button:focus { color: #66FF66; border: solid #66FF66; }
    Footer {
        background: #000000;
        color: #00CC33;
        dock: bottom;
        height: 1;
        padding: 0 1;
    }
    #status_bar {
        background: #000000;
        color: #66FF66;
        dock: bottom;
        width: 100%;
        height: 1;
        padding: 0 1;
    }
    """

    BINDINGS = [
        Binding("ctrl+q", "app.pop_screen", "Back"),
        Binding("escape", "app.pop_screen", "Back"),
    ]

    def __init__(self, main_app: "PromptSmithApp") -> None:
        super().__init__()
        self.main_app = main_app

    def compose(self) -> ComposeResult:
        yield VerticalScroll(
            Label("┌─ SETTINGS ─┐", id="title"),
            _styled_button("[ Edit Profiles ]", id="edit_profiles"),
            _styled_button("[ Switch Model ]", id="switch_model"),
            _styled_button("[ Export Source Code ]", id="export_source"),
            _styled_button("[ Export Profiles ]", id="export_profiles"),
            _styled_button("[ Export Templates ]", id="export_templates"),
            _styled_button("[ Download LLM Models (presets) ]", id="download_models"),
            Label("Or download from a custom .gguf URL:"),
            Input(
                placeholder="https://huggingface.co/<repo>/resolve/main/<file>.gguf",
                id="custom_model_url",
            ),
            _styled_button("[ Download From URL ]", id="download_custom"),
            _styled_button("[ Model Status ]", id="model_status"),
            _styled_button("[ About ]", id="about"),
            _styled_button("[ Back ]", id="back"),
            Static(self.main_app.status_message, id="status_bar"),
        )
        yield Footer()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "back":
            self.app.pop_screen()
        elif event.button.id == "edit_profiles":
            self.app.push_screen(ProfileEditorScreen(self.main_app))
        elif event.button.id == "switch_model":
            self.app.push_screen(ModelSwitchScreen(self.main_app))
        elif event.button.id == "export_source":
            self.action_export_source_code()
        elif event.button.id == "export_profiles":
            self.action_export_profiles()
        elif event.button.id == "export_templates":
            self.action_export_templates()
        elif event.button.id == "download_custom":
            self.action_download_custom_model()
        elif event.button.id == "download_models":
            self.action_download_models()
        elif event.button.id == "model_status":
            self.action_model_status()
        elif event.button.id == "about":
            self.app.push_screen(AboutScreen())

    def action_export_source_code(self) -> None:
        try:
            from promptsmith.scripts.export import export_source_code
            path = export_source_code(root=_PROJECT_ROOT)
            message = f"Source code exported -> {path}"
        except Exception as exc:
            message = f"Export failed: {exc}"
        self.app.pop_screen()
        self.main_app.status_message = message

    def action_export_profiles(self) -> None:
        try:
            import zipfile
            from datetime import datetime
            timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
            export_path = _PROJECT_ROOT / "exports" / f"promptsmith-profiles-{timestamp}.zip"
            export_path.parent.mkdir(parents=True, exist_ok=True)

            # Built-in first, user overrides second (by filename) - matches
            # the same precedence used when the app actually loads these.
            merged: dict = {f.name: f for f in _PROFILES_DIR.glob("*.yaml")}
            merged.update({f.name: f for f in _USER_PROFILES_DIR.glob("*.yaml")})

            with zipfile.ZipFile(export_path, "w", zipfile.ZIP_DEFLATED) as zf:
                for name, f in merged.items():
                    zf.write(f, f"profiles/{name}")
            
            message = f"Profiles exported -> {export_path}"
        except Exception as exc:
            message = f"Profile export failed: {exc}"
        self.app.pop_screen()
        self.main_app.status_message = message

    def action_export_templates(self) -> None:
        try:
            import zipfile
            from datetime import datetime
            timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
            export_path = _PROJECT_ROOT / "exports" / f"promptsmith-templates-{timestamp}.zip"
            export_path.parent.mkdir(parents=True, exist_ok=True)

            merged: dict = {f.name: f for f in _TEMPLATES_DIR.glob("*.yaml")}
            merged.update({f.name: f for f in _USER_TEMPLATES_DIR.glob("*.yaml")})

            with zipfile.ZipFile(export_path, "w", zipfile.ZIP_DEFLATED) as zf:
                for name, f in merged.items():
                    zf.write(f, f"templates/{name}")
            
            message = f"Templates exported -> {export_path}"
        except Exception as exc:
            message = f"Template export failed: {exc}"
        self.app.pop_screen()
        self.main_app.status_message = message

    def action_download_models(self) -> None:
        self.main_app.status_message = "Downloading models in background (this can take a while)..."
        self.app.pop_screen()
        self.main_app.start_model_download()

    def action_model_status(self) -> None:
        try:
            from promptsmith.utils.system_utils import MODEL_DIR
            if MODEL_DIR.exists():
                models = sorted(MODEL_DIR.glob("*.gguf"))
            else:
                models = []

            if models:
                sizes = [f"{m.name} ({m.stat().st_size / (1024*1024):.0f}MB)" for m in models]
                on_disk = "On disk: " + ", ".join(sizes)
            else:
                on_disk = "On disk: none (Settings > Download LLM Models)"

            refiner = self.main_app.refiner
            last_backend = getattr(refiner, "last_backend_used", None)
            last_model = getattr(refiner, "last_model_used", None)
            if last_backend in ("llm", "hybrid") and last_model:
                last_used = f"Last refine used: {last_backend} ({last_model})"
            elif last_backend:
                last_used = f"Last refine used: {last_backend}"
            else:
                last_used = "Last refine used: (none yet)"

            self.main_app.status_message = f"{on_disk} | {last_used}"
        except Exception as e:
            self.main_app.status_message = f"Model status error: {e}"

    def action_download_custom_model(self) -> None:
        url = self.query_one("#custom_model_url", Input).value.strip()
        if not url:
            self.main_app.status_message = "Enter a .gguf URL first."
            return
        self.main_app.status_message = f"Downloading from URL in background..."
        self.app.pop_screen()
        self.main_app.start_custom_model_download(url)


class ModelSwitchScreen(Screen):
    """Lets the user pick which downloaded .gguf model llm/hybrid profiles
    should use, without touching config.yaml by hand. Download itself is
    unchanged - this only points the app at a model already on disk."""

    CSS = """
    Screen {
        background: #000000;
        color: #00CC33;
    }
    Container, VerticalScroll {
        layout: vertical;
        width: 100%;
        height: 100%;
        border: double #00CC33;
        padding: 1 2;
    }
    Label#title {
        text-style: bold;
        color: #66FF66;
        dock: top;
        padding: 1 2;
    }
    Button {
        background: #000000;
        color: #00CC33;
        border: solid #00CC33;
        width: 100%;
        padding: 0 2;
        margin: 0 0 1 0;
    }
    Button:focus { color: #66FF66; border: solid #66FF66; }
    Select {
        border: solid #00CC33;
        color: #00CC33;
        background: #000000;
        height: 3;
        margin: 0 0 1 0;
    }
    Footer {
        background: #000000;
        color: #00CC33;
        dock: bottom;
        height: 1;
        padding: 0 1;
    }
    #status_bar {
        background: #000000;
        color: #66FF66;
        dock: bottom;
        width: 100%;
        height: 1;
        padding: 0 1;
    }
    """

    BINDINGS = [
        Binding("ctrl+q", "app.pop_screen", "Back"),
        Binding("escape", "app.pop_screen", "Back"),
    ]

    _AUTO = "__auto__"

    def __init__(self, main_app: "PromptSmithApp") -> None:
        super().__init__()
        self.main_app = main_app

    def _discover_models(self) -> list[Path]:
        from promptsmith.utils.system_utils import MODEL_DIR
        if not MODEL_DIR.exists():
            return []
        return sorted(MODEL_DIR.glob("*.gguf"))

    def compose(self) -> ComposeResult:
        models = self._discover_models()
        configured = self.main_app.config_manager.get("llm.model_path")

        options = [("Auto (first available in models/)", self._AUTO)]
        for m in models:
            label = f"{m.name} ({m.stat().st_size / (1024*1024):.0f}MB)"
            options.append((label, str(m)))

        # If the configured path isn't one of the discovered files (moved,
        # renamed, or a custom download URL filename), surface it anyway
        # rather than silently hiding the user's actual current setting.
        if configured and configured not in [v for _, v in options]:
            options.append((f"{Path(configured).name} (configured, not found on disk)", configured))

        current_value = configured if configured in [v for _, v in options] else self._AUTO

        yield VerticalScroll(
            Label("┌─ SWITCH MODEL ─┐", id="title"),
            Label("Model used by 'llm' and 'hybrid' backend profiles:"),
            Select(options, id="model_select", value=current_value, allow_blank=False),
            Label("Download new models from Settings > Download LLM Models."),
            _styled_button("[ Use Selected Model ]", id="apply_model"),
            _styled_button("[ Back ]", id="back"),
            Static(self.main_app.status_message, id="status_bar"),
        )
        yield Footer()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "back":
            self.app.pop_screen()
        elif event.button.id == "apply_model":
            self.action_apply_model()

    def action_apply_model(self) -> None:
        try:
            value = self.query_one("#model_select", Select).value
        except Exception as e:
            self.query_one("#status_bar", Static).update(f"Error: {e}")
            return

        if value is None or value == self._AUTO:
            self.main_app.config_manager.set("llm.model_path", None)
            message = "Model set to Auto (first available model in models/)."
        else:
            self.main_app.config_manager.set("llm.model_path", value)
            message = f"Model switched -> {Path(value).name}"

        self.main_app.status_message = message
        self.app.pop_screen()


class ProfileEditorScreen(Screen):
    """Form-based editor for profile YAML files, so a non-technical user
    (e.g. a product owner) never has to hand-edit YAML directly. Editing a
    built-in profile creates a user-space override (same mechanism the
    profile loader already uses for user customization); the shipped copy
    is never modified or removed."""

    CSS = """
    Screen {
        background: #000000;
        color: #00CC33;
    }
    Container, VerticalScroll {
        layout: vertical;
        width: 100%;
        height: 100%;
        border: double #00CC33;
        padding: 1 2;
    }
    Label#title {
        text-style: bold;
        color: #66FF66;
        dock: top;
        padding: 1 2;
    }
    Label.field_label {
        color: #00CC33;
        padding-top: 1;
    }
    Input, Select {
        border: solid #00CC33;
        background: #000000;
        color: #00CC33;
        height: 3;
    }
    Input:focus, Select:focus { border: solid #66FF66; }
    TextArea {
        border: solid #00CC33;
        background: #000000;
        color: #00CC33;
        height: 5;
    }
    TextArea:focus { border: solid #66FF66; }
    Static#editor_hint {
        color: #33FF33;
        padding: 1 0;
    }
    Static#backend_legend {
        color: #1E661E;
        padding: 0 0 1 0;
        height: auto;
    }
    #button_row {
        layout: horizontal;
        height: auto;
        padding-top: 1;
    }
    #button_row Button {
        margin: 0 1 0 0;
        width: auto;
        padding: 0 2;
        background: #000000;
        color: #00CC33;
        border: solid #00CC33;
    }
    #button_row Button:focus { color: #66FF66; border: solid #66FF66; }
    Footer {
        background: #000000;
        color: #00CC33;
        dock: bottom;
        height: 1;
        padding: 0 1;
    }
    #status_bar {
        background: #000000;
        color: #66FF66;
        dock: bottom;
        width: 100%;
        height: 1;
        padding: 0 1;
    }
    """

    BINDINGS = [
        Binding("ctrl+q", "app.pop_screen", "Back"),
        Binding("escape", "app.pop_screen", "Back"),
        # Without these, ctrl+s / ctrl+a fall through to the App's own
        # BINDINGS (save_config / analyze), which act on the main screen's
        # hidden prompt input and a status bar that isn't the one visible
        # here - so the keys appeared to "do nothing" while silently
        # running the wrong action against invisible state.
        Binding("ctrl+s", "save", "Save"),
        Binding("ctrl+a", "noop_analyze", "Analyze (n/a)"),
    ]

    _NEW = "__new__"

    def __init__(self, main_app: "PromptSmithApp") -> None:
        super().__init__()
        self.main_app = main_app
        self._loaded_id: Optional[str] = None  # profile id currently populating the form
        self._loaded_was_builtin: bool = False  # whether that id was a built-in (not yet overridden)

    @staticmethod
    def _slugify(text: str) -> str:
        slug = re.sub(r"[^a-z0-9]+", "-", text.strip().lower()).strip("-")
        return slug or "new-profile"

    def compose(self) -> ComposeResult:
        profile_options = [("+ New Profile", self._NEW)] + [
            (p, p) for p in sorted(self.main_app.profile_manager.list_profiles())
        ]
        # Container has overflow: hidden by default (clips), unlike
        # VerticalScroll which scrolls - with 11 fields + 2 TextAreas this
        # form is taller than most terminal windows, so a plain Container
        # here silently clipped the Vendor/Backend fields and the
        # Save/Delete/Back buttons below the visible area with no way to
        # reach them (not even via keyboard focus, since hidden overflow
        # doesn't auto-scroll focus into view the way VerticalScroll does).
        yield VerticalScroll(
            Label("┌─ PROFILE EDITOR ─┐", id="title"),
            Label("Load existing profile (or start a new one):"),
            Select(profile_options, id="profile_picker", value=self._NEW),
            Static("Creating a new profile.", id="editor_hint"),
            Label("Profile ID (filename, lowercase-hyphenated):", classes="field_label"),
            Input(placeholder="e.g. golang-developer", id="id_input"),
            Label("Display Name:", classes="field_label"),
            Input(placeholder="e.g. Golang Developer", id="name_input"),
            Label("Role (required):", classes="field_label"),
            Input(placeholder="e.g. Golang Developer", id="role_input"),
            Label("Domain / expertise areas (one per line):", classes="field_label"),
            TextArea(id="domain_input"),
            Label("Tone:", classes="field_label"),
            Input(placeholder="e.g. Technical and precise", id="tone_input"),
            Label("Format:", classes="field_label"),
            Input(placeholder="e.g. Markdown with code blocks", id="format_input"),
            Label("Constraints (one per line):", classes="field_label"),
            TextArea(id="constraints_input"),
            Label("Vendor:", classes="field_label"),
            Input(placeholder="generic", id="vendor_input"),
            Label("Backend:", classes="field_label"),
            Select(
                [(v, k) for k, v in [("rule", "rule (deterministic)"), ("llm", "llm (model-generated)"), ("hybrid", "hybrid (rules + model polish)")]],
                id="backend_input",
                value="rule",
                allow_blank=False,
            ),
            Static(
                "rule = guarantees constraints verbatim, no model needed. "
                "llm = model writes freely (best for advisory/unstructured roles). "
                "hybrid = rules build the scaffold, model polishes it (best for structured technical roles).",
                id="backend_legend",
            ),
            Container(
                _styled_button("[ Save ]", id="save_profile"),
                _styled_button("[ Delete ]", id="delete_profile"),
                _styled_button("[ Back ]", id="back"),
                id="button_row",
            ),
            Static(self.main_app.status_message, id="status_bar"),
        )
        yield Footer()

    def on_mount(self) -> None:
        self._set_form_new()

    def on_select_changed(self, event: Select.Changed) -> None:
        # Select.set_options() (used after Save/Delete to add/remove entries)
        # transiently resets the widget's value to Select.BLANK and posts a
        # Changed message for it before our follow-up `.value = ...` takes
        # effect. Both are delivered asynchronously, so ignore the blank
        # blip here rather than let it clobber the just-set status message.
        if _is_blank_select_value(event.value):
            return
        if event.select.id == "profile_picker":
            if event.value == self._NEW:
                self._set_form_new()
            else:
                self._load_profile(event.value)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "back":
            self.app.pop_screen()
        elif event.button.id == "save_profile":
            self.action_save()
        elif event.button.id == "delete_profile":
            self.action_delete()

    def _set_form_new(self) -> None:
        self._loaded_id = None
        self._loaded_was_builtin = False
        self.query_one("#id_input", Input).value = ""
        self.query_one("#name_input", Input).value = ""
        self.query_one("#role_input", Input).value = ""
        self.query_one("#domain_input", TextArea).text = ""
        self.query_one("#tone_input", Input).value = ""
        self.query_one("#format_input", Input).value = ""
        self.query_one("#constraints_input", TextArea).text = ""
        self.query_one("#vendor_input", Input).value = "generic"
        self.query_one("#backend_input", Select).value = "rule"
        self.query_one("#editor_hint", Static).update("Creating a new profile.")

    def _load_profile(self, profile_id: str) -> None:
        try:
            data = self.main_app.profile_manager.get_profile(profile_id)
        except Exception as e:
            self.query_one("#status_bar", Static).update(f"Could not load '{profile_id}': {e}")
            return

        self._loaded_id = profile_id
        is_user = self.main_app.profile_manager.is_user_defined(profile_id)
        self._loaded_was_builtin = not is_user
        self.query_one("#id_input", Input).value = profile_id
        self.query_one("#name_input", Input).value = data.get("name", "")
        self.query_one("#role_input", Input).value = data.get("role", "")
        self.query_one("#domain_input", TextArea).text = "\n".join(data.get("domain", []) or [])
        self.query_one("#tone_input", Input).value = data.get("tone", "")
        self.query_one("#format_input", Input).value = data.get("format", "")
        self.query_one("#constraints_input", TextArea).text = "\n".join(data.get("constraints", []) or [])
        self.query_one("#vendor_input", Input).value = data.get("vendor", "generic")
        self.query_one("#backend_input", Select).value = data.get("backend", "rule")

        if is_user:
            hint = f"Editing your custom profile '{profile_id}'."
        else:
            hint = (
                f"Editing built-in profile '{profile_id}' — saving creates your own copy; "
                f"the version shipped with the app is left untouched."
            )
        self.query_one("#editor_hint", Static).update(hint)

    def action_save(self) -> None:
        status = self.query_one("#status_bar", Static)

        raw_id = self.query_one("#id_input", Input).value.strip()
        role = self.query_one("#role_input", Input).value.strip()
        if not role:
            status.update("Role is required.")
            return

        profile_id = self._slugify(raw_id) if raw_id else self._slugify(
            self.query_one("#name_input", Input).value or role
        )

        domain = [line.strip() for line in self.query_one("#domain_input", TextArea).text.splitlines() if line.strip()]
        constraints = [line.strip() for line in self.query_one("#constraints_input", TextArea).text.splitlines() if line.strip()]
        name = self.query_one("#name_input", Input).value.strip() or profile_id
        tone = self.query_one("#tone_input", Input).value.strip() or "neutral"
        fmt = self.query_one("#format_input", Input).value.strip() or "text"
        vendor = self.query_one("#vendor_input", Input).value.strip() or "generic"
        backend = self.query_one("#backend_input", Select).value or "rule"

        # Preserve version across edits of an existing profile; start fresh
        # profiles at 1.
        version = 1
        if self._loaded_id:
            try:
                version = self.main_app.profile_manager.get_profile(self._loaded_id).get("version", 1)
            except Exception:
                version = 1

        data = {
            "name": name,
            "role": role,
            "domain": domain,
            "tone": tone,
            "format": fmt,
            "constraints": constraints,
            "vendor": vendor,
            "version": version,
            "backend": backend,
        }

        try:
            self.main_app.profile_manager.add_profile(profile_id, data)
        except Exception as e:
            status.update(f"Save failed: {e}")
            return

        previous_id = self._loaded_id
        renamed = previous_id is not None and previous_id != profile_id
        overwrote_builtin = self._loaded_was_builtin and not renamed
        self._loaded_id = profile_id
        self._loaded_was_builtin = False  # it's a user profile now, regardless of what it was
        self.main_app.refresh_profile_options()

        picker = self.query_one("#profile_picker", Select)
        picker.set_options(
            [("+ New Profile", self._NEW)]
            + [(p, p) for p in sorted(self.main_app.profile_manager.list_profiles())]
        )
        picker.value = profile_id
        self.query_one("#id_input", Input).value = profile_id

        # Show the actual file location every time (not just at load time) -
        # add_profile() always writes to profile_manager.user_dir when one
        # is configured, so this is the concrete answer to "where did my
        # save go", not just an assurance.
        user_dir = self.main_app.profile_manager.user_dir
        saved_path = f"{user_dir}/{profile_id}.yaml" if user_dir is not None else f"{profile_id}.yaml"

        if renamed:
            status.update(f"Saved as '{profile_id}' → {saved_path} (new copy — '{previous_id}' was left as-is).")
        elif overwrote_builtin:
            status.update(f"Saved '{profile_id}' → {saved_path} (your copy — the built-in version ships untouched).")
        else:
            status.update(f"Saved '{profile_id}' → {saved_path}.")
        self.query_one("#editor_hint", Static).update(f"Editing your custom profile '{profile_id}'.")

    def action_noop_analyze(self) -> None:
        """Ctrl+A is bound to 'Analyze' on the main screen; there's no
        equivalent concept for a profile definition, so make that explicit
        here instead of letting the key silently fall through to the main
        screen's action_analyze (which would run against a hidden prompt
        input and update a status bar you can't see)."""
        self.query_one("#status_bar", Static).update(
            "Analyze isn't available in the Profile Editor — it applies to prompts, not profiles."
        )

    def action_delete(self) -> None:
        status = self.query_one("#status_bar", Static)
        if not self._loaded_id:
            status.update("Nothing to delete - no profile loaded.")
            return
        if not self.main_app.profile_manager.is_user_defined(self._loaded_id):
            status.update("Built-in profiles can't be deleted, only overridden by saving your own version.")
            return
        try:
            self.main_app.profile_manager.delete_profile(self._loaded_id)
        except Exception as e:
            status.update(f"Delete failed: {e}")
            return
        deleted = self._loaded_id
        self.main_app.refresh_profile_options()
        picker = self.query_one("#profile_picker", Select)
        picker.set_options(
            [("+ New Profile", self._NEW)]
            + [(p, p) for p in sorted(self.main_app.profile_manager.list_profiles())]
        )
        picker.value = self._NEW
        self._set_form_new()
        status.update(f"Deleted '{deleted}'.")


def main() -> None:
    import sys as _sys

    configure_model_catalog()
    configure_runtime_model_behavior()

    if "--version" in _sys.argv or "-V" in _sys.argv:
        # Machine-checkable version output, also used by the build
        # scripts' post-build smoke test.
        print(f"{PRODUCT_NAME} {__version__} ({display_version()})")
        return

    try:
        PromptSmithApp().run()
    except KeyboardInterrupt:
        print("\nGoodbye!")
    except Exception as exc:
        logger.exception("Fatal error in PromptSmith-cli")
        print(f"Error: {type(exc).__name__}: {exc}")


if __name__ == "__main__":
    main()
