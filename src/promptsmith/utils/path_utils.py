"""Path resolution utilities for PromptSmith-cli."""

import logging
import sys
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


def is_frozen() -> bool:
    """True when running inside a PyInstaller-built executable (onefile or
    onedir - PyInstaller sets sys._MEIPASS identically for both: a temp
    extraction dir for onefile, the dist folder itself for onedir)."""
    return bool(getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"))


def get_project_root(from_file: Optional[Path] = None) -> Path:
    if is_frozen():
        # Deliberately NOT sys._MEIPASS: in a PyInstaller --onedir build,
        # that points at the hidden _internal/ folder holding the Python
        # runtime and dependencies. Resources meant to be user-visible and
        # directly editable (profiles/, templates/, models/) are instead
        # placed as siblings of the executable itself by the build script,
        # so resolve against sys.executable's directory - the top-level
        # folder someone actually sees when they open the distributed app.
        root = Path(sys.executable).resolve().parent
        logger.debug(f"Running frozen - using executable directory: {root}")
        return root

    if from_file is None:
        import inspect
        frame = inspect.currentframe()
        try:
            caller_frame = frame.f_back.f_back if frame and frame.f_back else frame
            if caller_frame and caller_frame.f_code:
                from_file = Path(caller_frame.f_code.co_filename)
        finally:
            del frame
    if from_file is None:
        from_file = Path.cwd()
    path = Path(from_file).resolve()
    for parent in [path] + list(path.parents):
        if (parent / "pyproject.toml").exists():
            logger.debug(f"Found project root: {parent}")
            return parent
    # No pyproject.toml above us and not frozen: we are running from an
    # installed wheel (pip install promptsmith-cli). There is no "project
    # root" in that mode - fall back to a per-user writable directory so
    # things resolved against the root (config.yaml, exports/) still have
    # a sane, persistent home instead of crashing at import time.
    fallback = Path.home() / ".promptsmith"
    fallback.mkdir(parents=True, exist_ok=True)
    logger.debug(
        f"No project root (pyproject.toml) found from {from_file}; "
        f"running as an installed package - using {fallback}"
    )
    return fallback


def get_builtin_data_dir() -> Path:
    """Directory holding the built-in profiles/ and templates/ shipped
    inside the promptsmith package itself (src/promptsmith/data/).

    This is the canonical copy for source checkouts and wheel installs.
    Frozen (PyInstaller) builds never reach this - get_asset_path()
    resolves their assets as visible siblings of the executable first.
    """
    from importlib.resources import files

    return Path(str(files("promptsmith") / "data"))


def get_asset_path(asset_name: str, from_file: Optional[Path] = None) -> Path:
    """Resolve a bundled asset directory (profiles/, templates/, models/).

    The resolution order depends on how the app is running, because the
    two modes have opposite correct answers:

    Frozen (PyInstaller) build - prefer a visible sibling folder next to
    the executable:
      1. <root>/<asset_name> if it exists - the build script places
         profiles/, templates/, and models/ there as user-editable
         folders, and that copy is authoritative.
      2. packaged promptsmith/data/<asset_name> as a fallback.
      3. <root>/<asset_name> even if absent (e.g. models/ pre-download).

    Source checkout or wheel install - prefer the package's own data dir:
      1. packaged promptsmith/data/<asset_name> if it exists - this is the
         canonical built-in copy.
      2. <root>/<asset_name> if it exists - supports a source checkout
         that keeps top-level asset folders.
      3. <root>/<asset_name> even if absent.

    Why the split: in a wheel install get_project_root() falls back to
    ~/.promptsmith, which is ALSO where the user profile/template
    directories live. If we checked <root>/<asset_name> first there, then
    the moment the app created ~/.promptsmith/profiles as the *user*
    override dir, the next launch would resolve that same (initially
    empty) folder as the *built-in* dir - handing ProfileManager the same
    path for both and dropping all 35 built-ins to zero. Preferring the
    packaged copy in non-frozen mode makes the built-in lookup independent
    of the user-data root entirely.
    """
    project_root = get_project_root(from_file)
    root_asset = project_root / asset_name

    try:
        packaged = get_builtin_data_dir() / asset_name
    except Exception as exc:  # pragma: no cover - importlib.resources edge cases
        logger.debug(f"Packaged data lookup failed for {asset_name}: {exc}")
        packaged = None

    if is_frozen():
        # Frozen: visible sibling folder wins.
        if root_asset.is_dir():
            logger.debug(f"Asset path for {asset_name} (frozen sibling): {root_asset}")
            return root_asset
        if packaged is not None and packaged.is_dir():
            logger.debug(f"Asset path for {asset_name} (packaged): {packaged}")
            return packaged
        return root_asset

    # Source / wheel: packaged built-in copy wins, so the built-in lookup
    # never collides with the user-data root.
    if packaged is not None and packaged.is_dir():
        logger.debug(f"Asset path for {asset_name} (packaged): {packaged}")
        return packaged
    if root_asset.is_dir():
        logger.debug(f"Asset path for {asset_name} (root): {root_asset}")
        return root_asset
    logger.debug(f"Asset path for {asset_name} (root, absent): {root_asset}")
    return root_asset


def get_user_data_dir() -> Path:
    """User-space directory for anything that should survive a
    reinstall/update - custom profiles, custom templates, logs.

    In a frozen/portable build this must live next to the executable, as a
    sibling of the exposed profiles/, templates/, and models/ folders - not
    in the OS home directory. A portable distribution's entire point is
    that a user's customizations travel with the app folder; redirecting
    saves into a hidden ~/.promptsmith made edits invisible next to the
    folders someone was actually looking at, indistinguishable from the
    save silently failing. A distinct 'user_data' subfolder (rather than
    reusing profiles/ or templates/ directly) avoids colliding with the
    read-only built-in files those folders already contain, which get
    replaced wholesale on the next build/reinstall.

    Running from source keeps the ~/.promptsmith default (out of the
    source tree, matching prior behavior). PROMPTSMITH_LOG_DIR overrides
    either way, for anyone who wants explicit control regardless of mode.
    """
    import os
    if "PROMPTSMITH_LOG_DIR" in os.environ:
        d = Path(os.environ["PROMPTSMITH_LOG_DIR"])
    elif is_frozen():
        d = Path(sys.executable).resolve().parent / "user_data"
    else:
        d = Path.home() / ".promptsmith"
    d.mkdir(parents=True, exist_ok=True)
    return d