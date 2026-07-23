"""PromptSmith application launcher with release-candidate UI corrections."""

from __future__ import annotations

import sys

from textual.binding import Binding
from textual.content import Content

from promptsmith._version import PRODUCT_NAME, __version__, display_version
from promptsmith.cli.app import PromptSmithApp as BasePromptSmithApp
from promptsmith.scripts.model_catalog import configure_model_catalog


class PromptSmithApp(BasePromptSmithApp):
    """Main application with conventional editor bindings and literal hints."""

    BINDINGS = [
        Binding("ctrl+q", "quit", "Quit"),
        Binding("ctrl+enter", "analyze", "Analyze"),
        Binding("ctrl+r", "refine", "Refine"),
        Binding("ctrl+y", "copy", "Copy"),
        Binding("ctrl+s", "save_config", "Save Config"),
        Binding("down", "scroll_down", "Scroll Down"),
        Binding("up", "scroll_up", "Scroll Up"),
    ]

    def _update_analysis_display(self) -> None:
        if self.current_analysis is None:
            # Static parses strings as Textual markup. Content keeps the
            # instruction literal instead of consuming bracketed key labels.
            self._analysis_output.update(
                Content("Enter a prompt, then press Ctrl+Enter to analyze or Ctrl+R to refine.")
            )
            self._readiness_indicator.update("")
            self._readiness_indicator.remove_class("not_ready")
            return
        super()._update_analysis_display()


def main() -> None:
    configure_model_catalog()
    if "--version" in sys.argv or "-V" in sys.argv:
        print(f"{PRODUCT_NAME} {__version__} ({display_version()})")
        return
    try:
        PromptSmithApp().run()
    except KeyboardInterrupt:
        print("\nGoodbye!")
    except Exception as exc:
        # The base module owns the configured file logger. Avoid printing
        # prompt content or backend payloads here.
        print(f"Error: {type(exc).__name__}")


if __name__ == "__main__":
    main()
