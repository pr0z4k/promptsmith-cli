import argparse
import shutil
from pathlib import Path
import zipfile

from promptsmith.core.config import ConfigManager
from promptsmith.utils.system_utils import MODEL_DIR

def package_models(output_path: Path):
    """Package models into a zip file."""
    if not MODEL_DIR.exists():
        print(f"No models found in {MODEL_DIR}")
        return

    with zipfile.ZipFile(output_path, "w", zipfile.ZIP_DEFLATED) as zipf:
        for model_path in MODEL_DIR.glob("*"):
            if model_path.is_file():
                zipf.write(model_path, arcname=model_path.name)

    print(f"Models packaged to {output_path}")

def main():
    parser = argparse.ArgumentParser(description="Package PromptSmith-cli models")
    parser.add_argument("output_path", type=str, help="Path to the output zip file")
    args = parser.parse_args()

    package_models(Path(args.output_path))

if __name__ == "__main__":
    main()
