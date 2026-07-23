"""
Template management for PromptSmith-cli.

Loads and manages prompt templates from a YAML directory with validation.
"""

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from .config_store import YAMLConfigStore
from .exceptions import TemplateNotFoundError
from .schemas import TemplateSchema

logger = logging.getLogger(__name__)


class TemplateManager(YAMLConfigStore):
    def __init__(self, templates_dir: Path = Path("templates"), user_dir: Optional[Path] = None):
        super().__init__(templates_dir, TemplateSchema, user_dir=user_dir)
        self.templates_dir = templates_dir

    def get_template(self, name: str) -> Dict[str, Any]:
        template = self.get_config(name)
        if not template:
            raise TemplateNotFoundError(name, f"Template '{name}' not found in {self.templates_dir}")
        return template

    def add_template(self, name: str, template_data: Dict) -> None:
        try:
            super().add_config(name, template_data)
        except Exception as e:
            logger.error(f"Failed to add template {name}: {e}")
            raise

    def delete_template(self, name: str) -> bool:
        try:
            return super().delete_config(name)
        except Exception as e:
            logger.error(f"Failed to delete template {name}: {e}")
            raise

    def list_templates(self) -> List[str]:
        return self.list_configs()

    def get_all_templates(self) -> Dict[str, Dict[str, Any]]:
        return {name: self.get_config(name) for name in self.list_configs()}