"""Filesystem utilities for PromptSmith-cli."""

import logging
from pathlib import Path
from typing import Union

logger = logging.getLogger(__name__)


def ensure_directory(dir_path: Union[str, Path]) -> Path:
    dir_path = Path(dir_path)
    try:
        dir_path.mkdir(parents=True, exist_ok=True)
        logger.debug(f"Ensured directory exists: {dir_path}")
        return dir_path
    except OSError as e:
        from ..core.exceptions import FilesystemError
        logger.error(f"Failed to create directory {dir_path}: {e}")
        raise FilesystemError(f"Cannot create directory {dir_path}: {e}") from e