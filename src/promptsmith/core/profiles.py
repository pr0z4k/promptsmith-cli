"""
Profile management for PromptSmith-cli.

Loads and manages persona profiles from a YAML directory with validation.
"""

import logging
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

from .config_store import YAMLConfigStore
from .exceptions import ProfileNotFoundError
from .schemas import ProfileSchema

logger = logging.getLogger(__name__)


class ProfileManager(YAMLConfigStore):
    def __init__(self, profiles_dir: Path = Path("profiles"), user_dir: Optional[Path] = None):
        super().__init__(profiles_dir, ProfileSchema, user_dir=user_dir)
        self.profiles_dir = profiles_dir

    def resolve_id(self, name_or_id: str) -> Optional[str]:
        """Resolve either a canonical profile id (e.g. 'react-developer',
        already what the TUI always passes) or a human-readable display
        name (e.g. 'React Developer', what PromptAnalyzer's
        TYPE_PROFILE_MAP and recommended_profile return) to the actual
        file id. Returns None if nothing matches.

        Without this, any caller that passes a display name - as
        IntentCompiler does when no profile is explicitly chosen, since it
        falls back to analysis.recommended_profile - gets a silent
        ProfileNotFoundError, caught upstream and downgraded to "just
        return the original prompt unchanged with a warning", with no
        indication the requested profile was ever actually applied.
        """
        if not name_or_id:
            return None
        if name_or_id in self.list_configs():
            return name_or_id
        slug = re.sub(r"[^a-z0-9]+", "-", name_or_id.strip().lower()).strip("-")
        if slug in self.list_configs():
            return slug
        for profile_id in self.list_configs():
            try:
                if self.get_config(profile_id).get("name", "").strip().lower() == name_or_id.strip().lower():
                    return profile_id
            except Exception:
                continue
        return None

    def get_profile(self, name: str) -> Dict[str, Any]:
        profile = self.get_config(name)
        if profile:
            return profile
        resolved = self.resolve_id(name)
        if resolved:
            profile = self.get_config(resolved)
            if profile:
                return profile
        raise ProfileNotFoundError(name, f"Profile '{name}' not found in {self.profiles_dir}")

    def add_profile(self, name: str, profile_data: Dict) -> None:
        try:
            super().add_config(name, profile_data)
        except Exception as e:
            logger.error(f"Failed to add profile {name}: {e}")
            raise

    def delete_profile(self, name: str) -> bool:
        try:
            return super().delete_config(name)
        except Exception as e:
            logger.error(f"Failed to delete profile {name}: {e}")
            raise

    def list_profiles(self) -> List[str]:
        return self.list_configs()

    def get_all_profiles(self) -> Dict[str, Dict[str, Any]]:
        return {name: self.get_config(name) for name in self.list_configs()}