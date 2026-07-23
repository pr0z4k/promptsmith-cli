"""Single source of truth for the PromptSmith-cli version.

The version is defined exactly once, in pyproject.toml. At install time
(pip, editable install, or wheel) setuptools writes it into the package
metadata, and this module reads it back via importlib.metadata - so
bumping pyproject.toml automatically updates every runtime reference,
including the About screen and the --version flag.

PyInstaller builds must bundle that metadata for this to keep working
frozen: both build scripts pass --copy-metadata promptsmith-cli.
"""

import re
from importlib.metadata import PackageNotFoundError, version

#: Distribution name on PyPI / in pyproject.toml ([project].name)
DIST_NAME = "promptsmith-cli"

#: Human-facing product name, used in the UI and documentation.
PRODUCT_NAME = "PromptSmith-cli"

#: Project home and support links (About screen, docs, --version output).
PROJECT_URL = "https://github.com/pr0z4k/promptsmith-cli"
SUPPORT_URL = "https://github.com/pr0z4k/promptsmith-cli/issues"

try:
    __version__ = version(DIST_NAME)
except PackageNotFoundError:  # running from a raw checkout without install
    __version__ = "0.0.0.dev0"

_PRE_LABELS = {"a": "Alpha", "b": "Beta", "rc": "RC"}


def display_version(raw: str = None) -> str:
    """Format a PEP 440 version for humans: '0.6.0b1' -> '0.6 Beta'.

    Trailing zero release segments are trimmed (1.0.0 -> 1.0) and
    pre-release markers are spelled out (b -> Beta, a -> Alpha, rc -> RC).
    Anything unparseable is returned untouched rather than hidden.
    """
    raw = raw if raw is not None else __version__
    m = re.match(r"^(\d+(?:\.\d+)*)(?:\.?(a|b|rc)(\d+))?(?:\+.*)?$", raw)
    if not m:
        return raw
    release, pre, _pre_n = m.groups()
    parts = release.split(".")
    while len(parts) > 2 and parts[-1] == "0":
        parts.pop()
    out = ".".join(parts)
    if pre:
        out += f" {_PRE_LABELS[pre]}"
    return out