import argparse
import json
from pathlib import Path

from promptsmith.core.config import ConfigManager
from promptsmith.core.profiles import ProfileManager
from promptsmith.core.templates import TemplateManager

def export_data(output_dir: Path, include_profiles: bool = True, include_templates: bool = True):
    """Export PromptSmith-cli data to JSON files."""
    output_dir.mkdir(parents=True, exist_ok=True)

    if include_profiles:
        profile_manager = ProfileManager()
        profiles = {name: profile for name, profile in profile_manager._cache.items()}
        with open(output_dir / "profiles.json", "w", encoding="utf-8") as f:
            json.dump(profiles, f, indent=2)

    if include_templates:
        template_manager = TemplateManager()
        templates = {name: template for name, template in template_manager._cache.items()}
        with open(output_dir / "templates.json", "w", encoding="utf-8") as f:
            json.dump(templates, f, indent=2)

    config_manager = ConfigManager()
    with open(output_dir / "config.json", "w", encoding="utf-8") as f:
        json.dump(config_manager._config, f, indent=2)

def main():
    parser = argparse.ArgumentParser(description="Export PromptSmith-cli data")
    parser.add_argument("output_dir", type=str, help="Directory to export data to")
    parser.add_argument("--no-profiles", action="store_false", dest="include_profiles", help="Exclude profiles from export")
    parser.add_argument("--no-templates", action="store_false", dest="include_templates", help="Exclude templates from export")
    args = parser.parse_args()

    export_data(Path(args.output_dir), args.include_profiles, args.include_templates)
    print(f"Data exported to {args.output_dir}")

if __name__ == "__main__":
    main()
