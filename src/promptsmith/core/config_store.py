"""
YAML-backed configuration store for PromptSmith-cli.

Provides abstract base class and implementation for loading YAML configs
from directories with validation support.
"""

import logging
import os
import re
import tempfile
from abc import ABC
from pathlib import Path
from typing import Dict, List, Optional, Type

import yaml

logger = logging.getLogger(__name__)

_CONFIG_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")


class YAMLConfigStore(ABC):
    def __init__(
        self,
        config_dir: Path,
        config_schema: Optional[Type] = None,
        user_dir: Optional[Path] = None,
    ):
        """
        config_dir: built-in/bundled directory, read-only in spirit (never
            written to by this class).
        user_dir: optional user-space directory. If given, it's scanned in
            addition to config_dir, and entries here override any
            same-named entry from config_dir. New entries and deletions are
            written here, never to config_dir.
        """
        self.config_dir = Path(config_dir)
        self.user_dir = Path(user_dir) if user_dir is not None else None
        self.config_schema = config_schema
        self._cache: Dict[str, Dict] = {}
        self._source: Dict[str, Path] = {}
        self._load_configs()

    @staticmethod
    def _validate_name(name: str) -> str:
        """Validate a filename stem without permitting path traversal."""

        if not isinstance(name, str) or not _CONFIG_NAME_RE.fullmatch(name):
            raise ValueError(
                "Config name must be 1-128 characters and contain only letters, "
                "numbers, '.', '_' or '-'; path separators are not allowed"
            )
        if name in {".", ".."}:
            raise ValueError("Config name cannot be '.' or '..'")
        return name

    def _ensure_dir(self, directory: Path) -> None:
        try:
            directory.mkdir(parents=True, exist_ok=True)
        except OSError as e:
            from .exceptions import FilesystemError

            raise FilesystemError(f"Cannot create config directory {directory}: {e}") from e

    def _ensure_config_dir(self) -> None:
        self._ensure_dir(self.config_dir)

    def _load_dir(self, directory: Path) -> None:
        if not directory.exists():
            return
        for config_file in sorted(directory.glob("*.yaml")):
            try:
                if config_file.is_symlink():
                    logger.warning("Skipping symlinked config file: %s", config_file)
                    continue
                with config_file.open("r", encoding="utf-8") as f:
                    config_data = yaml.safe_load(f)

                if config_data is None:
                    continue
                if not isinstance(config_data, dict):
                    raise ValueError("YAML document root must be a mapping")

                if self.config_schema is not None:
                    validated = self._validate_config(config_data, config_file.name)
                    self._cache[config_file.stem] = validated
                else:
                    self._cache[config_file.stem] = config_data
                self._source[config_file.stem] = directory
                logger.debug("Loaded config: %s (from %s)", config_file.stem, directory)
            except yaml.YAMLError as e:
                logger.error("Invalid YAML in %s: %s", config_file.name, e)
            except ValueError as e:
                logger.error("Validation error in %s: %s", config_file.name, e)
            except OSError as e:
                logger.error("Failed to load config %s: %s", config_file.name, e)

    def _load_configs(self) -> None:
        self._cache = {}
        self._source = {}
        self._ensure_config_dir()
        self._load_dir(self.config_dir)
        if self.user_dir is not None:
            self._ensure_dir(self.user_dir)
            self._load_dir(self.user_dir)

    def is_user_defined(self, name: str) -> bool:
        return self.user_dir is not None and self._source.get(name) == self.user_dir

    def _validate_config(self, config_data: Dict, source: str) -> Dict:
        if self.config_schema is None:
            return config_data
        try:
            if hasattr(self.config_schema, "validate"):
                return self.config_schema.validate(config_data)
            return config_data
        except Exception as e:
            raise ValueError(f"Validation failed for {source}: {e}") from e

    def get_config(self, name: str) -> Dict:
        self._validate_name(name)
        if name not in self._cache:
            self._load_configs()
        return self._cache.get(name, {})

    def invalidate(self, name: str) -> None:
        self._validate_name(name)
        self._cache.pop(name, None)
        self._source.pop(name, None)

    def list_configs(self) -> List[str]:
        return list(self._cache.keys())

    @staticmethod
    def _atomic_write_yaml(config_path: Path, config_data: Dict) -> None:
        if config_path.is_symlink():
            raise OSError(f"Refusing to overwrite symlink: {config_path}")

        temp_path: Optional[Path] = None
        fd: Optional[int] = None
        try:
            fd, raw_temp_path = tempfile.mkstemp(
                prefix=f".{config_path.name}.",
                suffix=".tmp",
                dir=config_path.parent,
            )
            temp_path = Path(raw_temp_path)
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                fd = None
                yaml.safe_dump(
                    config_data,
                    f,
                    sort_keys=False,
                    default_flow_style=False,
                    allow_unicode=True,
                )
                f.flush()
                os.fsync(f.fileno())
            try:
                os.chmod(temp_path, 0o600)
            except OSError:
                pass
            os.replace(temp_path, config_path)
            temp_path = None
        finally:
            if fd is not None:
                os.close(fd)
            if temp_path is not None:
                temp_path.unlink(missing_ok=True)

    def add_config(self, name: str, config_data: Dict) -> None:
        name = self._validate_name(name)
        if not isinstance(config_data, dict):
            raise ValueError("Config data must be a mapping")
        validated = self._validate_config(config_data, name)
        target_dir = self.user_dir if self.user_dir is not None else self.config_dir
        self._ensure_dir(target_dir)
        config_path = target_dir / f"{name}.yaml"
        try:
            self._atomic_write_yaml(config_path, validated)
            logger.info("Added config: %s (in %s)", name, target_dir)
            self._cache[name] = validated
            self._source[name] = target_dir
        except (OSError, yaml.YAMLError) as e:
            from .exceptions import FilesystemError

            raise FilesystemError(f"Cannot save config {name}: {e}") from e

    def delete_config(self, name: str) -> bool:
        name = self._validate_name(name)
        if name not in self._cache:
            return False
        source_dir = self._source.get(name, self.user_dir or self.config_dir)
        config_path = source_dir / f"{name}.yaml"
        try:
            if config_path.is_symlink():
                raise OSError(f"Refusing to delete symlinked config: {config_path}")
            if config_path.exists():
                config_path.unlink()
            del self._cache[name]
            self._source.pop(name, None)
            logger.info("Deleted config: %s (from %s)", name, source_dir)
            return True
        except OSError as e:
            from .exceptions import FilesystemError

            logger.error("Failed to delete config %s: %s", name, e)
            raise FilesystemError(f"Cannot delete config {name}: {e}") from e

    def reload(self) -> None:
        self._cache = {}
        self._source = {}
        self._load_configs()
