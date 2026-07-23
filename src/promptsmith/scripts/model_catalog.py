"""Stable preset-model catalog for PromptSmith-cli.

Preset downloads deliberately use PromptSmith's own streamed HTTPS downloader.
That path is thread-safe inside the Textual worker, validates redirects, checks
GGUF content and SHA-256, fsyncs the partial file, and atomically promotes it.
"""

from __future__ import annotations

from typing import Any

from promptsmith.scripts import package_models


MODEL_CATALOG: dict[str, dict[str, Any]] = {
    "phi4-mini": {
        "name": "Phi-4-mini-instruct",
        "file": "microsoft_Phi-4-mini-instruct-Q4_K_M.gguf",
        "url": (
            "https://huggingface.co/bartowski/microsoft_Phi-4-mini-instruct-GGUF"
            "/resolve/main/microsoft_Phi-4-mini-instruct-Q4_K_M.gguf"
        ),
        "sha256": "01999f17c39cc3074afae5e9c539bc82d45f2dd7faa3917c66cbef76fce8c0c2",
        "ram_required_gb": 16,
        "chat_format": "phi3",
    }
}


def configure_model_catalog() -> None:
    """Install the corrected, checksummed built-in model catalog."""

    package_models.MODELS_CONFIG["phi4-mini"] = dict(MODEL_CATALOG["phi4-mini"])
