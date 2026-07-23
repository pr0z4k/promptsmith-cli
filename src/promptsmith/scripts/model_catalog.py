"""Stable preset-model acquisition through the Hugging Face Hub API.

The UI previously depended on long ``/resolve/`` URLs. Those URLs are brittle
when a repository moves, changes storage backends, or requires Xet redirects.
This module identifies a preset by repository and filename, lets
``huggingface_hub`` resolve the current download route, then validates and
atomically promotes the GGUF into PromptSmith's model directory.
"""

from __future__ import annotations

import hashlib
import os
import shutil
import tempfile
from pathlib import Path
from typing import Any, Callable, Mapping, Optional

from promptsmith.scripts import package_models
from promptsmith.utils.system_utils import MODEL_DIR

ProgressCallback = Callable[[str, int, int], None]
_CHUNK_SIZE = 1024 * 1024

MODEL_CATALOG: dict[str, dict[str, Any]] = {
    "phi4-mini": {
        "name": "Phi-4-mini-instruct",
        "repo_id": "bartowski/microsoft_Phi-4-mini-instruct-GGUF",
        "file": "microsoft_Phi-4-mini-instruct-Q4_K_M.gguf",
        "sha256": "01999f17c39cc3074afae5e9c539bc82d45f2dd7faa3917c66cbef76fce8c0c2",
        "ram_required_gb": 16,
        "chat_format": "phi-3",
    }
}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(_CHUNK_SIZE), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _install_hub_model(
    model_key: str,
    config: Mapping[str, Any],
    progress_callback: Optional[ProgressCallback] = None,
) -> None:
    try:
        from huggingface_hub import hf_hub_download
    except ImportError as exc:  # pragma: no cover - packaging regression guard
        raise RuntimeError(
            "Missing dependency: huggingface-hub. Reinstall PromptSmith-cli normally."
        ) from exc

    repo_id = str(config["repo_id"])
    filename = package_models._safe_filename(str(config["file"]))
    expected_sha256 = str(config["sha256"]).lower()
    destination = package_models._confined_model_path(filename)

    if destination.exists() and not destination.is_symlink():
        if package_models.is_valid_gguf(destination) and _sha256(destination) == expected_sha256:
            if progress_callback:
                progress_callback(model_key, 1, 1)
            return

    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    if MODEL_DIR.is_symlink():
        raise package_models.DownloadSecurityError(
            f"Refusing to download through symlinked model directory: {MODEL_DIR}"
        )

    part_path = destination.with_name(destination.name + ".part")
    package_models._cleanup_partial(part_path)

    with tempfile.TemporaryDirectory(prefix="promptsmith-hf-", dir=MODEL_DIR) as temporary:
        temporary_dir = Path(temporary)
        if progress_callback:
            progress_callback(model_key, 0, 0)

        cached_path = Path(
            hf_hub_download(
                repo_id=repo_id,
                filename=filename,
                local_dir=temporary_dir,
            )
        )
        if cached_path.is_symlink() or not cached_path.is_file():
            raise package_models.InvalidModelFileError(
                f"{model_key}: Hugging Face did not return a regular model file"
            )
        if not package_models.is_valid_gguf(cached_path):
            raise package_models.InvalidModelFileError(
                f"{model_key}: downloaded content is not a valid GGUF model"
            )

        actual_sha256 = _sha256(cached_path)
        if actual_sha256 != expected_sha256:
            raise package_models.InvalidModelFileError(
                f"{model_key}: SHA-256 mismatch; expected {expected_sha256}, got {actual_sha256}"
            )

        try:
            with cached_path.open("rb") as source, part_path.open("xb") as target:
                shutil.copyfileobj(source, target, length=_CHUNK_SIZE)
                target.flush()
                os.fsync(target.fileno())
            if destination.is_symlink():
                raise package_models.DownloadSecurityError(
                    f"Refusing to replace symlinked model: {destination}"
                )
            os.replace(part_path, destination)
        except BaseException:
            package_models._cleanup_partial(part_path)
            raise

    if progress_callback:
        size = destination.stat().st_size
        progress_callback(model_key, size, size)


def configure_model_catalog() -> None:
    """Install the stable catalog and route catalog entries through Hub."""

    package_models.MODELS_CONFIG["phi4-mini"] = dict(MODEL_CATALOG["phi4-mini"])
    original_download_model = package_models.download_model

    if getattr(original_download_model, "_promptsmith_hub_aware", False):
        return

    def hub_aware_download_model(
        model_key: str,
        config: Mapping[str, Any],
        progress_callback: Optional[ProgressCallback] = None,
    ) -> None:
        if config.get("repo_id"):
            _install_hub_model(model_key, config, progress_callback)
            return
        original_download_model(model_key, dict(config), progress_callback)

    hub_aware_download_model._promptsmith_hub_aware = True  # type: ignore[attr-defined]
    package_models.download_model = hub_aware_download_model  # type: ignore[assignment]
