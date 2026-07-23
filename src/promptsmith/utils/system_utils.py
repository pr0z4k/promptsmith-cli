"""System utilities for PromptSmith-cli."""

import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

_psutil = None


def _get_psutil():
    global _psutil
    if _psutil is None:
        try:
            import psutil
            _psutil = psutil
        except ImportError:
            logger.warning("psutil not available, system memory info will be limited")
            _psutil = None
    return _psutil


_MODEL_DIR: Optional[Path] = None


def get_model_dir() -> Path:
    global _MODEL_DIR
    if _MODEL_DIR is None:
        from .path_utils import get_asset_path
        _MODEL_DIR = get_asset_path("models", __file__)
    return _MODEL_DIR


MODEL_DIR = get_model_dir()


def get_available_ram() -> float:
    psutil = _get_psutil()
    if psutil is not None:
        try:
            return psutil.virtual_memory().available / (1024 ** 3)
        except Exception as e:
            logger.warning(f"Failed to get available RAM: {e}")
    return -1.0


def ensure_model_dir() -> Path:
    model_dir = get_model_dir()
    try:
        model_dir.mkdir(parents=True, exist_ok=True)
        logger.debug(f"Ensured models directory exists: {model_dir}")
        return model_dir
    except OSError as e:
        from ..core.exceptions import FilesystemError
        logger.error(f"Failed to create models directory {model_dir}: {e}")
        raise FilesystemError(f"Cannot create models directory {model_dir}: {e}") from e


def check_model(model_name: str) -> bool:
    model_dir = get_model_dir()
    model_path = model_dir / model_name
    exists = model_path.exists()
    logger.debug(f"Model {model_name} exists: {exists}")
    return exists