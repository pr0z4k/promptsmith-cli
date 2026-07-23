"""
YAML-backed configuration store for PromptSmith-cli.

Provides abstract base class and implementation for loading YAML configs
from directories with validation support.
"""

import logging
from abc import ABC
from pathlib import Path
from typing import Dict, List, Optional, Type
import yaml

logger = logging.getLogger(__name__)

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
            same-named entry from config_dir - lets a user customize a
            built-in profile without touching the shipped copy, which
            would just be overwritten on the next update anyway. New
            entries (add_config) and deletions are written here, never to
            config_dir, so built-in defaults are never mutated in place.
        """
        self.config_dir = Path(config_dir)
        self.user_dir = Path(user_dir) if user_dir is not None else None
        self.config_schema = config_schema
        self._cache: Dict[str, Dict] = {}
        self._source: Dict[str, Path] = {}
        self._load_configs()

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
                with open(config_file, "r", encoding="utf-8") as f:
                    config_data = yaml.safe_load(f)

                if config_data:
                    if self.config_schema is not None:
                        validated = self._validate_config(config_data, config_file.name)
                        self._cache[config_file.stem] = validated
                    else:
                        self._cache[config_file.stem] = config_data
                    self._source[config_file.stem] = directory
                    logger.debug(f"Loaded config: {config_file.stem} (from {directory})")
            except yaml.YAMLError as e:
                logger.error(f"Invalid YAML in {config_file.name}: {e}")
            except ValueError as e:
                logger.error(f"Validation error in {config_file.name}: {e}")
            except OSError as e:
                logger.error(f"Failed to load config {config_file.name}: {e}")

    def _load_configs(self) -> None:
        self._cache = {}
        self._source = {}
        self._ensure_config_dir()
        # Built-in defaults first, then user overrides on top - later wins
        # on a name collision, so a user's own copy of e.g. "vibe-coding"
        # takes precedence over the bundled one without editing it.
        self._load_dir(self.config_dir)
        if self.user_dir is not None:
            self._ensure_dir(self.user_dir)
            self._load_dir(self.user_dir)

    def is_user_defined(self, name: str) -> bool:
        """True if this entry came from the user directory (either an
        override of a built-in name, or a name only the user has)."""
        return self.user_dir is not None and self._source.get(name) == self.user_dir

    def _validate_config(self, config_data: Dict, source: str) -> Dict:
        if self.config_schema is None:
            return config_data
        try:
            if hasattr(self.config_schema, 'validate'):
                return self.config_schema.validate(config_data)
            else:
                return config_data
        except Exception as e:
            raise ValueError(f"Validation failed for {source}: {e}") from e

    def get_config(self, name: str) -> Dict:
        if name not in self._cache:
            self._load_configs()  # Refresh cache on miss
        return self._cache.get(name, {})

    def invalidate(self, name: str) -> None:
        self._cache.pop(name, None)
        self._source.pop(name, None)

    def list_configs(self) -> List[str]:
        return list(self._cache.keys())

    def add_config(self, name: str, config_data: Dict) -> None:
        if not name:
            raise ValueError("Config name cannot be empty")
        validated = self._validate_config(config_data, name)
        # Always write new/edited configs to user_dir when available, never
        # to config_dir (the built-in defaults) - keeps user additions
        # separate from what ships with the app, so they survive an update.
        target_dir = self.user_dir if self.user_dir is not None else self.config_dir
        self._ensure_dir(target_dir)
        config_path = target_dir / f"{name}.yaml"
        try:
            with open(config_path, "w", encoding="utf-8") as f:
                yaml.dump(validated, f, sort_keys=False, default_flow_style=False)
            logger.info(f"Added config: {name} (in {target_dir})")
            self._cache[name] = validated  # Keep cache in sync with what was just written
            self._source[name] = target_dir
        except OSError as e:
            from .exceptions import FilesystemError
            raise FilesystemError(f"Cannot save config {name}: {e}") from e

    def delete_config(self, name: str) -> bool:
        if name not in self._cache:
            return False
        # Only ever delete from user_dir (or config_dir if there's no
        # user_dir at all) - never remove a built-in file that happens to
        # be shadowed by a user override; deleting the user copy should
        # just reveal the built-in one again on next reload.
        source_dir = self._source.get(name, self.user_dir or self.config_dir)
        config_path = source_dir / f"{name}.yaml"
        try:
            if config_path.exists():
                config_path.unlink()
            del self._cache[name]
            self._source.pop(name, None)
            logger.info(f"Deleted config: {name} (from {source_dir})")
            return True
        except OSError as e:
            from .exceptions import FilesystemError
            logger.error(f"Failed to delete config {name}: {e}")
            raise FilesystemError(f"Cannot delete config {name}: {e}") from e

    def reload(self) -> None:
        self._cache = {}
        self._source = {}
        self._load_configs()
