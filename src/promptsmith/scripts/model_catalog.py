"""Stable preset-model catalog for PromptSmith-cli.

Preset downloads deliberately use PromptSmith's own streamed HTTPS downloader.
That path is thread-safe inside the Textual worker, validates redirects, checks
GGUF content and SHA-256, fsyncs the partial file, and atomically promotes it.

Built-in presets may provide multiple equivalent sources. Every source must
produce the exact same checksummed artifact; a fallback never weakens identity
verification merely because a host or branch moved.
"""

from __future__ import annotations

import logging
from typing import Any, Callable, Optional

from promptsmith.scripts import package_models

logger = logging.getLogger(__name__)

MODEL_CATALOG: dict[str, dict[str, Any]] = {
    "phi4-mini": {
        "name": "Phi-4-mini-instruct",
        "file": "microsoft_Phi-4-mini-instruct-Q4_K_M.gguf",
        "sources": [
            (
                "https://huggingface.co/bartowski/microsoft_Phi-4-mini-instruct-GGUF"
                "/resolve/915429c/microsoft_Phi-4-mini-instruct-Q4_K_M.gguf"
            ),
            (
                "https://huggingface.co/bartowski/microsoft_Phi-4-mini-instruct-GGUF"
                "/resolve/main/microsoft_Phi-4-mini-instruct-Q4_K_M.gguf"
            ),
        ],
        "sha256": "01999f17c39cc3074afae5e9c539bc82d45f2dd7faa3917c66cbef76fce8c0c2",
        "ram_required_gb": 16,
        "chat_format": "phi3",
    }
}

ProgressCallback = Callable[[str, int, int], None]


def _download_model_from_catalog(
    model_key: str,
    cfg: dict[str, Any],
    progress_callback: Optional[ProgressCallback] = None,
) -> None:
    """Download a preset from the first healthy source with matching content.

    The underlying downloader retains retries, redirect validation, GGUF checks,
    checksum verification, partial cleanup, fsync, and atomic promotion. This
    wrapper only adds ordered source failover for trusted built-in presets.
    """

    filename = package_models._safe_filename(str(cfg["file"]))
    model_path = package_models._confined_model_path(filename)
    configured_sources = cfg.get("sources")
    if configured_sources is None:
        configured_sources = [cfg["url"]]
    if not isinstance(configured_sources, (list, tuple)) or not configured_sources:
        raise ValueError(f"{model_key}: preset must define at least one source")

    errors: list[str] = []
    for source_number, source in enumerate(configured_sources, start=1):
        try:
            package_models._stream_download(
                model_key,
                str(source),
                model_path,
                progress_callback=progress_callback,
                expected_sha256=cfg.get("sha256"),
            )
            if source_number > 1:
                logger.info(
                    "%s: downloaded successfully from fallback source %s/%s",
                    model_key,
                    source_number,
                    len(configured_sources),
                )
            return
        except package_models.DownloadSecurityError:
            raise
        except Exception as exc:
            errors.append(f"source {source_number}: {exc}")
            logger.warning(
                "%s: preset source %s/%s failed: %s",
                model_key,
                source_number,
                len(configured_sources),
                exc,
            )

    detail = "; ".join(errors)
    raise RuntimeError(
        f"Download failed for {model_key} from all {len(configured_sources)} "
        f"configured sources: {detail}"
    )


def configure_model_catalog() -> None:
    """Install the checksummed catalog and resilient preset download wrapper."""

    phi_config = dict(MODEL_CATALOG["phi4-mini"])
    # Keep ``url`` for compatibility with code and extensions that still inspect
    # the original single-source field.
    phi_config["url"] = phi_config["sources"][0]
    package_models.MODELS_CONFIG["phi4-mini"] = phi_config
    package_models.download_model = _download_model_from_catalog
