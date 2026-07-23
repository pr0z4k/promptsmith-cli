"""
Export utility for PromptSmith-cli.

Exports profiles, templates, config, and optionally models to a zip archive.
"""

import logging
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


def export_promptsmith(
    root: Path = Path("."),
    output_dir: Optional[Path] = None,
    include_models: bool = False,
    include_profiles: bool = True,
    include_templates: bool = True,
) -> Path:
    root = Path(root)
    if output_dir is None:
        output_dir = root / "exports"
    try:
        output_dir.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        from promptsmith.core.exceptions import FilesystemError
        logger.error(f"Cannot create output directory {output_dir}: {e}")
        raise FilesystemError(f"Cannot create output directory {output_dir}: {e}") from e

    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    export_path = output_dir / f"PromptSmith-cli-Export-{timestamp}.zip"

    logger.info(f"Exporting PromptSmith-cli to {export_path}")

    try:
        with zipfile.ZipFile(export_path, "w", zipfile.ZIP_DEFLATED) as zf:
            if include_profiles:
                profiles_dir = root / "profiles"
                if profiles_dir.exists():
                    for f in profiles_dir.glob("*.yaml"):
                        arcname = f"profiles/{f.name}"
                        logger.debug(f"Adding {f} as {arcname}")
                        zf.write(f, arcname)

            if include_templates:
                templates_dir = root / "templates"
                if templates_dir.exists():
                    for f in templates_dir.glob("*.yaml"):
                        arcname = f"templates/{f.name}"
                        logger.debug(f"Adding {f} as {arcname}")
                        zf.write(f, arcname)

            config = root / "config.yaml"
            if config.exists():
                logger.debug(f"Adding {config}")
                zf.write(config, "config.yaml")

            if include_models:
                models_dir = root / "models"
                if models_dir.exists():
                    for f in models_dir.glob("*.gguf"):
                        arcname = f"models/{f.name}"
                        logger.debug(f"Adding {f} as {arcname}")
                        zf.write(f, arcname)

        logger.info(f"Export completed: {export_path}")
        return export_path
        
    except Exception as e:
        from promptsmith.core.exceptions import FilesystemError
        logger.error(f"Export failed: {e}")
        if export_path.exists():
            export_path.unlink()
        raise FilesystemError(f"Export failed: {e}") from e


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )
    export_path = export_promptsmith()
    print(f"Export created: {export_path}")


# Directories/files that must never end up inside a full-application export,
# even though some of them live directly under the project root alongside
# everything that should be included.
_FULL_EXPORT_EXCLUDE_DIRS = {
    ".git", ".venv", "venv", "__pycache__", ".pytest_cache",
    "models", "exports", "build", "dist", ".pre-commit-cache",
    "user_data",
}
_FULL_EXPORT_EXCLUDE_SUFFIXES = {".pyc", ".gguf", ".log", ".db"}

# Top-level files worth including if present - source, packaging, and docs,
# but not local/machine-specific state like config.yaml (that's exported
# separately, deliberately, via export_promptsmith()).
_FULL_EXPORT_ROOT_FILES = [
    "pyproject.toml", "README.md", "ARCHITECTURE.md", "CHANGELOG.md",
    "BUILD.md", "LICENSE", "build_cli.sh", "build_windows.bat",
    ".pre-commit-config.yaml",
]


def export_source_code(
    root: Path = Path("."),
    output_dir: Optional[Path] = None,
) -> Path:
    """Export the project's source code - source, packaging files, and
    docs - not just profiles/templates/config.yaml (that's what
    export_promptsmith() does; this is a genuinely different, larger export
    meant for handing to a teammate to build themselves - it does NOT
    include a Python runtime or compiled dependencies, so it's source for
    rebuilding, not a runnable application on its own). Excludes anything
    environment-specific or huge: .venv, __pycache__, downloaded models,
    prior exports.
    """
    root = Path(root)
    if output_dir is None:
        output_dir = root / "exports"
    try:
        output_dir.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        from promptsmith.core.exceptions import FilesystemError
        logger.error(f"Cannot create output directory {output_dir}: {e}")
        raise FilesystemError(f"Cannot create output directory {output_dir}: {e}") from e

    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    export_path = output_dir / f"PromptSmith-cli-SourceCode-{timestamp}.zip"

    logger.info(f"Exporting PromptSmith-cli source code to {export_path}")

    def _should_skip(path: Path) -> bool:
        if path.suffix in _FULL_EXPORT_EXCLUDE_SUFFIXES:
            return True
        return any(part in _FULL_EXPORT_EXCLUDE_DIRS for part in path.parts)

    try:
        with zipfile.ZipFile(export_path, "w", zipfile.ZIP_DEFLATED) as zf:
            # Full source tree.
            src_dir = root / "src"
            if src_dir.exists():
                for f in src_dir.rglob("*"):
                    if f.is_file() and not _should_skip(f.relative_to(root)):
                        arcname = str(f.relative_to(root))
                        zf.write(f, arcname)

            # Data directories.
            for dirname in ("profiles", "templates", "tools"):
                d = root / dirname
                if d.exists():
                    for f in d.rglob("*"):
                        if f.is_file() and not _should_skip(f.relative_to(root)):
                            zf.write(f, str(f.relative_to(root)))

            # Top-level packaging/docs files.
            for filename in _FULL_EXPORT_ROOT_FILES:
                f = root / filename
                if f.exists() and f.is_file():
                    zf.write(f, filename)

        logger.info(f"Source code export completed: {export_path}")
        return export_path

    except Exception as e:
        from promptsmith.core.exceptions import FilesystemError
        logger.error(f"Source code export failed: {e}")
        if export_path.exists():
            export_path.unlink()
        raise FilesystemError(f"Source code export failed: {e}") from e