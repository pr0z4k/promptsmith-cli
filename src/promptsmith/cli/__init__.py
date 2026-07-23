"""
PromptSmith-cli CLI package.

This package contains the command-line interface for PromptSmith-cli.

The PromptSmithApp import is intentionally lazy (via __getattr__ rather
than a top-level `from .app import ...`). Importing app eagerly here means
`python -m promptsmith.cli.app` imports the app module twice - once as
promptsmith.cli.app through this package init, once as __main__ - which
triggers a RuntimeWarning from runpy about a double import. Deferring the
import until PromptSmithApp is actually accessed avoids that entirely
while keeping `from promptsmith.cli import PromptSmithApp` working.
"""

__all__ = ["PromptSmithApp"]


def __getattr__(name):
    if name == "PromptSmithApp":
        from .app import PromptSmithApp

        return PromptSmithApp
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
