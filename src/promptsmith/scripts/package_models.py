"""Secure model download utility for PromptSmith-cli.

Downloads pre-configured GGUF models from HuggingFace or a user-supplied HTTPS
URL. Downloads are streamed to a sibling ``.part`` file, validated, flushed,
and atomically promoted to their final path.
"""

from __future__ import annotations

import hashlib
import ipaddress
import logging
import os
import re
import time
from pathlib import Path
from typing import Any, Callable, Dict, Optional
from urllib.parse import unquote, urlsplit

from promptsmith.utils.system_utils import MODEL_DIR

logger = logging.getLogger(__name__)

MODELS_CONFIG: Dict[str, Dict[str, Any]] = {
    "phi4-mini": {
        "name": "Phi-4-mini-instruct",
        "file": "microsoft_Phi-4-mini-instruct-Q4_K_M.gguf",
        "url": (
            "https://huggingface.co/bartowski/microsoft-Phi-4-mini-instruct-GGUF"
            "/resolve/main/microsoft_Phi-4-mini-instruct-Q4_K_M.gguf"
        ),
        "ram_required_gb": 16,
        "chat_format": "phi-3",
    },
    "tinyllama": {
        "name": "TinyLlama 1.1B",
        "file": "tinyllama-1.1b-chat-v1.0.Q4_K_M.gguf",
        "url": (
            "https://huggingface.co/TheBloke/TinyLlama-1.1B-Chat-v1.0-GGUF"
            "/resolve/main/tinyllama-1.1b-chat-v1.0.Q4_K_M.gguf"
        ),
        "ram_required_gb": 8,
        "chat_format": "zephyr",
    },
}

ProgressCallback = Callable[[str, int, int], None]
GGUF_MAGIC = b"GGUF"
CONNECT_TIMEOUT_SECONDS = 10
READ_TIMEOUT_SECONDS = 120
CHUNK_SIZE = 1024 * 1024
_FILENAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,254}$")
_SHA256_RE = re.compile(r"^[0-9a-fA-F]{64}$")
_RETRYABLE_STATUS_CODES = {408, 425, 429, 500, 502, 503, 504}


class InvalidModelFileError(RuntimeError):
    """Raised when downloaded content is not a usable GGUF model."""


class DownloadSecurityError(RuntimeError):
    """Raised when a URL, redirect, path, or target violates download policy."""


def is_valid_gguf(path: Path) -> bool:
    """Return whether ``path`` is a regular, non-symlink GGUF file."""

    try:
        if path.is_symlink() or not path.is_file():
            return False
        with path.open("rb") as fh:
            return fh.read(len(GGUF_MAGIC)) == GGUF_MAGIC
    except OSError:
        return False


def _validate_https_url(url: str, *, field: str = "URL") -> str:
    """Validate an HTTPS URL without credentials or fragments."""

    value = url.strip()
    if not value:
        raise ValueError(f"{field} cannot be empty")
    if any(ord(char) < 32 for char in value):
        raise ValueError(f"{field} contains control characters")

    parsed = urlsplit(value)
    if parsed.scheme.lower() != "https":
        raise ValueError(f"{field} must use HTTPS")
    if not parsed.hostname:
        raise ValueError(f"{field} must include a hostname")
    if parsed.username is not None or parsed.password is not None:
        raise ValueError(f"{field} must not contain embedded credentials")
    if parsed.fragment:
        raise ValueError(f"{field} must not contain a fragment")

    host = parsed.hostname
    if host.startswith("[") or host.endswith("]"):
        raise ValueError(f"{field} contains a malformed hostname")
    try:
        if ":" in host:
            ipaddress.ip_address(host)
    except ValueError as exc:
        raise ValueError(f"{field} contains an invalid IP address") from exc
    return value


def _validate_checksum(expected_sha256: Optional[str]) -> Optional[str]:
    if expected_sha256 is None:
        return None
    checksum = expected_sha256.strip().lower()
    if not _SHA256_RE.fullmatch(checksum):
        raise ValueError("SHA-256 checksum must contain exactly 64 hexadecimal characters")
    return checksum


def _safe_filename(name: str) -> str:
    """Validate a user-visible model filename as one plain GGUF basename."""

    candidate = unquote(name.strip())
    if not candidate:
        raise ValueError("Model filename cannot be empty")
    if candidate in {".", ".."}:
        raise ValueError("Model filename is invalid")
    if "/" in candidate or "\\" in candidate or Path(candidate).name != candidate:
        raise ValueError("Model filename must not contain path separators")
    if not _FILENAME_RE.fullmatch(candidate):
        raise ValueError(
            "Model filename must be 1-255 characters and contain only letters, "
            "numbers, '.', '_' or '-'"
        )
    if not candidate.lower().endswith(".gguf"):
        raise ValueError("Model filename must end with .gguf")
    return candidate


def _confined_model_path(filename: str) -> Path:
    name = _safe_filename(filename)
    root = MODEL_DIR.resolve()
    destination = MODEL_DIR / name
    if destination.parent.resolve() != root:
        raise DownloadSecurityError("Model destination escapes the configured model directory")
    return destination


def filename_from_url(url: str) -> str:
    """Derive a safe GGUF basename from a validated HTTPS URL."""

    validated = _validate_https_url(url)
    raw_name = unquote(Path(urlsplit(validated).path).name)
    if not raw_name:
        raw_name = "custom-model.gguf"
    sanitized = re.sub(r"[^A-Za-z0-9._-]", "_", raw_name)
    if not sanitized.lower().endswith(".gguf"):
        sanitized += ".gguf"
    if len(sanitized) > 255:
        sanitized = f"{sanitized[:-5][:250]}.gguf"
    return _safe_filename(sanitized)


def _cleanup_partial(part_path: Path) -> None:
    try:
        if part_path.is_symlink():
            raise DownloadSecurityError(f"Refusing to use symlinked partial file: {part_path}")
        if part_path.exists():
            part_path.unlink()
    except DownloadSecurityError:
        raise
    except OSError as exc:
        raise RuntimeError(f"Cannot remove partial model file {part_path}: {exc}") from exc


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(CHUNK_SIZE), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _stream_download(
    label: str,
    url: str,
    dest_path: Path,
    progress_callback: Optional[ProgressCallback] = None,
    max_attempts: int = 3,
    expected_sha256: Optional[str] = None,
) -> None:
    """Securely stream one GGUF model to ``dest_path``."""

    if max_attempts < 1:
        raise ValueError("max_attempts must be at least 1")
    source_url = _validate_https_url(url)
    checksum = _validate_checksum(expected_sha256)
    dest_path = Path(dest_path)

    if dest_path.is_symlink():
        raise DownloadSecurityError(f"Refusing to overwrite symlinked model: {dest_path}")
    if dest_path.exists():
        if is_valid_gguf(dest_path) and (checksum is None or _sha256_file(dest_path) == checksum):
            logger.info("%s: already downloaded, skipping", label)
            if progress_callback:
                progress_callback(label, 1, 1)
            return
        logger.warning("%s: existing model is invalid or fails checksum; replacing it", label)
        try:
            dest_path.unlink()
        except OSError as exc:
            raise RuntimeError(f"Cannot remove invalid model file {dest_path}: {exc}") from exc

    try:
        dest_path.parent.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise RuntimeError(f"Cannot create model directory {dest_path.parent}: {exc}") from exc
    if dest_path.parent.is_symlink():
        raise DownloadSecurityError(f"Refusing to write through symlinked directory: {dest_path.parent}")

    part_path = dest_path.with_name(dest_path.name + ".part")
    _cleanup_partial(part_path)

    try:
        import requests
    except ImportError as exc:
        raise RuntimeError("Missing dependency: requests. Install project download dependencies") from exc

    last_error: Optional[Exception] = None
    for attempt in range(1, max_attempts + 1):
        if attempt > 1:
            time.sleep(min(1.5 * attempt, 10))
        response = None
        try:
            logger.info("Downloading %s from %s", label, source_url)
            response = requests.get(
                source_url,
                stream=True,
                timeout=(CONNECT_TIMEOUT_SECONDS, READ_TIMEOUT_SECONDS),
                allow_redirects=True,
            )
            final_url = _validate_https_url(response.url or source_url, field="Redirect URL")
            response.raise_for_status()

            content_length = response.headers.get("content-length")
            try:
                total = int(content_length) if content_length else 0
            except (TypeError, ValueError) as exc:
                raise InvalidModelFileError("Server returned an invalid Content-Length header") from exc
            if total < 0:
                raise InvalidModelFileError("Server returned a negative Content-Length header")

            downloaded = 0
            last_reported_pct = -1
            digest = hashlib.sha256()
            with part_path.open("xb") as fh:
                for chunk in response.iter_content(chunk_size=CHUNK_SIZE):
                    if not chunk:
                        continue
                    fh.write(chunk)
                    digest.update(chunk)
                    downloaded += len(chunk)
                    if progress_callback:
                        pct = int(downloaded * 100 / total) if total > 0 else -1
                        if total <= 0 or pct != last_reported_pct:
                            last_reported_pct = pct
                            progress_callback(label, downloaded, total)
                fh.flush()
                os.fsync(fh.fileno())

            if total > 0 and downloaded != total:
                raise IOError(
                    f"Downloaded size ({downloaded} bytes) does not match expected size "
                    f"({total} bytes)"
                )
            if not is_valid_gguf(part_path):
                raise InvalidModelFileError(f"{label}: downloaded content is not a valid GGUF model")
            actual_checksum = digest.hexdigest()
            if checksum is not None and actual_checksum != checksum:
                raise InvalidModelFileError(
                    f"{label}: SHA-256 mismatch; expected {checksum}, got {actual_checksum}"
                )

            if dest_path.is_symlink():
                raise DownloadSecurityError(f"Refusing to replace symlinked model: {dest_path}")
            os.replace(part_path, dest_path)
            logger.info("%s: saved to %s (final source %s)", label, dest_path, final_url)
            if progress_callback:
                progress_callback(label, downloaded, total or downloaded)
            return

        except DownloadSecurityError:
            _cleanup_partial(part_path)
            raise
        except InvalidModelFileError:
            _cleanup_partial(part_path)
            raise
        except requests.HTTPError as exc:
            last_error = exc
            status = exc.response.status_code if exc.response is not None else None
            failure_url = getattr(exc.response, "url", None) or source_url
            is_xet_403 = status == 403 and (
                "xethub" in str(failure_url).lower() or "cas-bridge" in str(failure_url).lower()
            )
            retryable = is_xet_403 or status in _RETRYABLE_STATUS_CODES
            _cleanup_partial(part_path)
            if retryable and attempt < max_attempts:
                logger.warning(
                    "%s: transient HTTP failure %s (attempt %s/%s); retrying",
                    label,
                    status,
                    attempt,
                    max_attempts,
                )
                continue
            if is_xet_403:
                raise RuntimeError(
                    f"Download failed for {label}: HuggingFace Xet storage returned 403 "
                    f"after {max_attempts} attempts"
                ) from exc
            raise RuntimeError(f"Download failed for {label}: HTTP {status or 'error'}") from exc
        except (requests.ConnectionError, requests.Timeout, IOError, OSError) as exc:
            last_error = exc
            _cleanup_partial(part_path)
            if attempt < max_attempts:
                logger.warning(
                    "%s: transient download failure (attempt %s/%s): %s",
                    label,
                    attempt,
                    max_attempts,
                    exc,
                )
                continue
            raise RuntimeError(
                f"Download failed for {label} after {max_attempts} attempts: {exc}"
            ) from exc
        except requests.RequestException as exc:
            _cleanup_partial(part_path)
            raise RuntimeError(f"Download failed for {label}: {exc}") from exc
        finally:
            if response is not None:
                try:
                    response.close()
                except Exception:
                    pass

    raise RuntimeError(f"Download failed after {max_attempts} attempts: {last_error}")


def download_model(
    model_key: str,
    cfg: Dict[str, Any],
    progress_callback: Optional[ProgressCallback] = None,
) -> None:
    filename = _safe_filename(str(cfg["file"]))
    model_path = _confined_model_path(filename)
    _stream_download(
        model_key,
        str(cfg["url"]),
        model_path,
        progress_callback=progress_callback,
        expected_sha256=cfg.get("sha256"),
    )


def download_custom_model(
    url: str,
    filename: Optional[str] = None,
    progress_callback: Optional[ProgressCallback] = None,
    expected_sha256: Optional[str] = None,
) -> Path:
    """Download one custom GGUF model from HTTPS into ``MODEL_DIR``."""

    source_url = _validate_https_url(url)
    name = _safe_filename(filename) if filename is not None else filename_from_url(source_url)
    dest_path = _confined_model_path(name)
    _stream_download(
        name,
        source_url,
        dest_path,
        progress_callback=progress_callback,
        expected_sha256=expected_sha256,
    )
    return dest_path


def main(progress_callback: Optional[ProgressCallback] = None) -> Dict[str, Any]:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )
    results: Dict[str, Any] = {}
    for key, cfg in MODELS_CONFIG.items():
        try:
            download_model(key, cfg, progress_callback=progress_callback)
            results[key] = {"success": True, "error": None}
        except Exception as exc:
            logger.error("Failed to download %s: %s", key, exc)
            results[key] = {"success": False, "error": str(exc)}
    return results


if __name__ == "__main__":
    main()
