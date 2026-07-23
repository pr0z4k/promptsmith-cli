"""PromptSmith application launcher with release-candidate UI corrections."""

from __future__ import annotations

import sys

from textual.binding import Binding
from textual.content import Content

from promptsmith._version import PRODUCT_NAME, __version__, display_version
from promptsmith.cli.app import PromptSmithApp as BasePromptSmithApp
from promptsmith.core.runtime_model_fixes import configure_runtime_model_behavior
from promptsmith.scripts.model_catalog import configure_model_catalog


class PromptSmithApp(BasePromptSmithApp):
    """Main application with conventional editor bindings and literal hints."""

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

    def _update_analysis_display(self) -> None:
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
        super()._update_analysis_display()

    def action_select_prompt_all(self) -> None:
        """Select the complete prompt without relying on terminal Cmd+A."""

        self._prompt_input.focus()
        select_all = getattr(self._prompt_input, "action_select_all", None)
        if callable(select_all):
            select_all()
            self.status_message = "Prompt selected."
        else:
            self.status_message = "Select All is unavailable in this Textual version."


def main() -> None:
    configure_model_catalog()
    configure_runtime_model_behavior()
    if "--version" in sys.argv or "-V" in sys.argv:
        print(f"{PRODUCT_NAME} {__version__} ({display_version()})")
        return
    try:
        PromptSmithApp().run()
    except KeyboardInterrupt:
        print("\nGoodbye!")
    except Exception as exc:
        print(f"Error: {type(exc).__name__}")


if __name__ == "__main__":
    main()
