"""
Configuration management for PromptSmith-cli.

Provides YAML-backed configuration with support for nested settings
using dot notation (e.g., 'llm.model_path').
"""

import logging
import os
import shutil
import tempfile
from pathlib import Path
from typing import Any, Dict, Optional, TypedDict

import yaml

logger = logging.getLogger(__name__)


class LLMConfig(TypedDict, total=False):
    """Configuration for LLM backend."""

    model_path: Optional[str]
    min_ram_gb: int


class UIConfig(TypedDict, total=False):
    """UI configuration settings."""

    theme: str


class ConfigManager:
    """YAML-backed configuration manager with nested-key support.

    Configuration updates are written to a temporary sibling file, flushed to
    disk, and atomically promoted with :func:`os.replace`. The previous valid
    file is retained as ``<name>.bak`` so a malformed or interrupted external
    edit does not strand the application without usable configuration.
    """

    def __init__(self, config_path: Path = Path("config.yaml")):
        self.config_path = Path(config_path)
        self.backup_path = self.config_path.with_name(self.config_path.name + ".bak")
        self._config: Dict[str, Any] = {}
        self._auto_save = True

        try:
            self._ensure_config_dir()
            self._load()
        except Exception as e:
            logger.error("Failed to initialize ConfigManager: %s", e)
            raise

    def _ensure_config_dir(self) -> None:
        try:
            self.config_path.parent.mkdir(parents=True, exist_ok=True)
        except OSError as e:
            from .exceptions import FilesystemError

            raise FilesystemError(
                f"Cannot create config directory {self.config_path.parent}: {e}"
            ) from e

    @staticmethod
    def _read_yaml_mapping(path: Path) -> Dict[str, Any]:
        with path.open("r", encoding="utf-8") as f:
            loaded = yaml.safe_load(f)
        if loaded is None:
            return {}
        if not isinstance(loaded, dict):
            raise ValueError(f"Configuration root in {path} must be a mapping")
        return loaded

    def _load(self) -> None:
        if not self.config_path.exists():
            logger.info("Config file %s not found, using defaults", self.config_path)
            self._config = {}
            return

        try:
            self._config = self._read_yaml_mapping(self.config_path)
            logger.debug("Loaded configuration from %s", self.config_path)
            return
        except (yaml.YAMLError, ValueError, OSError) as primary_error:
            logger.error("Cannot load config file %s: %s", self.config_path, primary_error)

        if self.backup_path.exists():
            try:
                self._config = self._read_yaml_mapping(self.backup_path)
                logger.warning(
                    "Recovered configuration from backup %s after primary file failed",
                    self.backup_path,
                )
                return
            except (yaml.YAMLError, ValueError, OSError) as backup_error:
                logger.error("Cannot load config backup %s: %s", self.backup_path, backup_error)

        from .exceptions import FilesystemError

        raise FilesystemError(
            f"Configuration file {self.config_path} is unreadable or invalid and no valid "
            f"backup is available"
        )

    def _reject_symlink_target(self) -> None:
        """Do not overwrite a symlink supplied in place of the config file."""

        if self.config_path.is_symlink():
            from .exceptions import FilesystemError

            raise FilesystemError(
                f"Refusing to write configuration through symlink: {self.config_path}"
            )

    def save(self) -> None:
        self._ensure_config_dir()
        self._reject_symlink_target()

        temp_path: Optional[Path] = None
        try:
            if self.config_path.exists():
                shutil.copy2(self.config_path, self.backup_path)

            fd, raw_temp_path = tempfile.mkstemp(
                prefix=f".{self.config_path.name}.",
                suffix=".tmp",
                dir=self.config_path.parent,
            )
            temp_path = Path(raw_temp_path)
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as f:
                    yaml.safe_dump(
                        self._config,
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
                os.replace(temp_path, self.config_path)
                temp_path = None
            except Exception:
                try:
                    os.close(fd)
                except OSError:
                    pass
                raise

            logger.debug("Saved configuration to %s", self.config_path)
        except (OSError, yaml.YAMLError) as e:
            from .exceptions import FilesystemError

            raise FilesystemError(f"Cannot save config file {self.config_path}: {e}") from e
        finally:
            if temp_path is not None:
                try:
                    temp_path.unlink(missing_ok=True)
                except OSError:
                    logger.warning("Could not remove temporary config file %s", temp_path)

    def _get_nested(self, keys: list[str], config: Dict[str, Any]) -> Any:
        current: Any = config
        for key in keys:
            if isinstance(current, dict) and key in current:
                current = current[key]
            else:
                return None
        return current

    def _set_nested(self, keys: list[str], value: Any, config: Dict[str, Any]) -> None:
        current = config
        for key in keys[:-1]:
            existing = current.get(key)
            if existing is None:
                current[key] = {}
            elif not isinstance(existing, dict):
                raise ValueError(
                    f"Cannot set nested configuration key through non-mapping value: {key}"
                )
            current = current[key]
        current[keys[-1]] = value

    def get(self, key: str, default: Any = None) -> Any:
        if not key:
            return default
        keys = key.split(".")
        result = self._get_nested(keys, self._config)
        return result if result is not None else default

    def set(self, key: str, value: Any, save: bool = True) -> None:
        if not key:
            raise ValueError("Configuration key cannot be empty")
        keys = key.split(".")
        if any(not part for part in keys):
            raise ValueError("Configuration key segments cannot be empty")
        self._set_nested(keys, value, self._config)
        if self._auto_save and save:
            self.save()

    def update(self, updates: Dict[str, Any], save: bool = True) -> None:
        for key, value in updates.items():
            self.set(key, value, save=False)
        if self._auto_save and save:
            self.save()

    def get_llm_config(self) -> LLMConfig:
        return {
            "model_path": self.get("llm.model_path"),
            "min_ram_gb": self.get("llm.min_ram_gb", 16),
        }

    def set_llm_config(self, config: LLMConfig, save: bool = True) -> None:
        if config.get("model_path") is not None:
            self.set("llm.model_path", config["model_path"], save=False)
        if config.get("min_ram_gb") is not None:
            self.set("llm.min_ram_gb", config["min_ram_gb"], save=False)
        if save:
            self.save()

    def reload(self) -> None:
        self._config = {}
        self._load()
