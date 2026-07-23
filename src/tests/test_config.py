"""Tests for ConfigManager."""
import pytest
from pathlib import Path
from promptsmith.core.config import ConfigManager
import yaml


@pytest.fixture
def config_manager(tmp_path):
    config_path = tmp_path / "config.yaml"
    return ConfigManager(config_path)


@pytest.fixture
def config_with_data(tmp_path):
    config_path = tmp_path / "config.yaml"
    config_data = {
        "default_profile": "test-profile",
        "default_template": "test-template",
        "llm": {
            "model_path": "models/test.gguf",
            "min_ram_gb": 8,
        },
    }
    with open(config_path, "w") as f:
        yaml.dump(config_data, f)
    return ConfigManager(config_path)


def test_get_nested_key(config_with_data):
    assert config_with_data.get("default_profile") == "test-profile"
    assert config_with_data.get("default_template") == "test-template"
    assert config_with_data.get("llm.model_path") == "models/test.gguf"
    assert config_with_data.get("llm.min_ram_gb") == 8


def test_get_missing_key_returns_default(config_with_data):
    assert config_with_data.get("nonexistent") is None
    assert config_with_data.get("nonexistent", "default") == "default"
    assert config_with_data.get("llm.nonexistent", 42) == 42


def test_set_nested_key(config_manager):
    config_manager.set("default_profile", "new-profile")
    assert config_manager.get("default_profile") == "new-profile"
    
    config_manager.set("llm.model_path", "models/new.gguf")
    assert config_manager.get("llm.model_path") == "models/new.gguf"


def test_batch_update(config_manager):
    updates = {
        "default_profile": "batch-profile",
        "default_template": "batch-template",
        "llm.model_path": "models/batch.gguf",
    }
    config_manager.update(updates)
    assert config_manager.get("default_profile") == "batch-profile"
    assert config_manager.get("default_template") == "batch-template"
    assert config_manager.get("llm.model_path") == "models/batch.gguf"


def test_get_llm_config(config_with_data):
    llm_config = config_with_data.get_llm_config()
    assert llm_config["model_path"] == "models/test.gguf"
    assert llm_config["min_ram_gb"] == 8


def test_get_llm_config_defaults(config_manager):
    llm_config = config_manager.get_llm_config()
    assert llm_config["model_path"] is None
    assert llm_config["min_ram_gb"] == 16  # default


def test_set_llm_config(config_manager):
    config_manager.set_llm_config({
        "model_path": "models/custom.gguf",
        "min_ram_gb": 32,
    })
    assert config_manager.get("llm.model_path") == "models/custom.gguf"
    assert config_manager.get("llm.min_ram_gb") == 32


def test_save_and_load(config_manager, tmp_path):
    config_manager.set("test_key", "test_value")
    config_manager.save()
    
    # Create a new manager and verify it loads the saved data
    new_manager = ConfigManager(tmp_path / "config.yaml")
    assert new_manager.get("test_key") == "test_value"
