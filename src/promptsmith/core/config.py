"""
Configuration management for PromptSmith-cli.

Provides YAML-backed configuration with support for nested settings
using dot notation (e.g., 'llm.model_path').
"""

import logging
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
    """
    YAML-backed configuration manager with support for nested settings.
    
    Supports dot notation for nested keys (e.g., 'llm.model_path').
    Automatically creates config directory if it doesn't exist.
    """

    def __init__(self, config_path: Path = Path("config.yaml")):
        self.config_path = Path(config_path)
        self._config: Dict[str, Any] = {}
        self._auto_save = True
        
        try:
            self._ensure_config_dir()
            self._load()
        except Exception as e:
            logger.error(f"Failed to initialize ConfigManager: {e}")
            raise

    def _ensure_config_dir(self) -> None:
        try:
            self.config_path.parent.mkdir(parents=True, exist_ok=True)
        except OSError as e:
            from .exceptions import FilesystemError
            raise FilesystemError(f"Cannot create config directory {self.config_path.parent}: {e}") from e

    def _load(self) -> None:
        if self.config_path.exists():
            try:
                with open(self.config_path, "r", encoding="utf-8") as f:
                    self._config = yaml.safe_load(f) or {}
                logger.debug(f"Loaded configuration from {self.config_path}")
            except yaml.YAMLError as e:
                logger.error(f"Invalid YAML in config file {self.config_path}: {e}")
                raise
            except OSError as e:
                from .exceptions import FilesystemError
                raise FilesystemError(f"Cannot read config file {self.config_path}: {e}") from e
        else:
            logger.info(f"Config file {self.config_path} not found, using defaults")
            self._config = {}

    def save(self) -> None:
        try:
            self._ensure_config_dir()
            with open(self.config_path, "w", encoding="utf-8") as f:
                yaml.dump(self._config, f, sort_keys=False, default_flow_style=False)
            logger.debug(f"Saved configuration to {self.config_path}")
        except OSError as e:
            from .exceptions import FilesystemError
            raise FilesystemError(f"Cannot save config file {self.config_path}: {e}") from e

    def _get_nested(self, keys: list[str], config: Dict[str, Any]) -> Any:
        current = config
        for key in keys:
            if isinstance(current, dict) and key in current:
                current = current[key]
            else:
                return None
        return current

    def _set_nested(self, keys: list[str], value: Any, config: Dict[str, Any]) -> None:
        current = config
        for key in keys[:-1]:
            if key not in current:
                current[key] = {}
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