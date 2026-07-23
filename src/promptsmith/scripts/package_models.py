"""
Model download utility for PromptSmith-cli.

Downloads pre-configured LLM models from HuggingFace, or an arbitrary
user-supplied .gguf URL.
"""

import logging
import os
import re
import time
from pathlib import Path
from typing import Any, Callable, Dict, Optional

logger = logging.getLogger(__name__)

from promptsmith.utils.system_utils import MODEL_DIR

# NOTE: HuggingFace repos/filenames do change or get reorganized over time.
# If a preset 404s/401s, check the repo's "Files" tab on huggingface.co for
# the current filename, or use "Download From URL" in Settings instead.
MODELS_CONFIG: Dict[str, Dict[str, Any]] = {
    "phi4-mini": {
        "name": "Phi-4-mini-instruct",
        "file": "microsoft_Phi-4-mini-instruct-Q4_K_M.gguf",
        "url": (
            "https://huggingface.co/bartowski/microsoft_Phi-4-mini-instruct-GGUF"
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
"""Called as (label, bytes_downloaded, total_bytes). total_bytes is 0 if unknown."""


# Every valid GGUF file begins with these four ASCII bytes ("GGUF"). This is
# the format's magic number, checked by llama.cpp itself before it will load
# a model. Verifying it here is a microsecond read that catches the whole
# class of "this file is not actually a model": an empty download, an
# HTML error page or login wall saved under a .gguf name, or an
# unrelated file sitting where a model is expected. It does NOT detect a
# file that begins with a valid GGUF header and is then truncated or
# corrupted further in - that would need a full content hash,
# which is deliberately out of scope (a multi-second operation on a
# multi-GB file, for a much rarer failure). The goal is to fail fast and
# legibly here, rather than deep inside llama.cpp's native loader with an
# error that gives the user no idea the file itself is the problem.
GGUF_MAGIC = b"GGUF"


def is_valid_gguf(path: Path) -> bool:
    """True if `path` exists and starts with the GGUF magic number.

    Returns False (never raises) for a missing file, an unreadable file,
    or one too short to contain the magic - all of which mean "not a
    usable model" for the caller's purposes.
    """
    try:
        with open(path, "rb") as fh:
            return fh.read(len(GGUF_MAGIC)) == GGUF_MAGIC
    except OSError:
        return False


class InvalidModelFileError(RuntimeError):
    """Raised when a downloaded file is not a valid GGUF model."""


def _stream_download(
    label: str,
    url: str,
    dest_path: Path,
    progress_callback: Optional[ProgressCallback] = None,
    max_attempts: int = 3,
) -> None:
    """Shared streaming-download core used by both preset and custom-URL downloads.

    Retries on low-level, non-HTTP failures (e.g. transient OS/threading errors)
    since these are typically momentary rather than a problem with the URL itself.
    """
    if dest_path.exists():
        # A file being present is not proof it's a usable model - it could
        # have been corrupted on disk since it was written (bad copy,
        # interrupted sync, bit-rot), or an earlier version of this code
        # could have saved a non-model response under this name. Verify the
        # GGUF header before trusting it; if it's not valid, treat the file
        # as absent and re-download rather than skipping onto a broken file
        # that llama.cpp will later fail to load with an opaque native error.
        if is_valid_gguf(dest_path):
            logger.info(f"{label}: already downloaded, skipping.")
            if progress_callback:
                progress_callback(label, 1, 1)
            return
        logger.warning(
            f"{label}: existing file at {dest_path} is not a valid GGUF "
            f"(corrupt or incomplete) - re-downloading."
        )
        try:
            dest_path.unlink()
        except OSError as e:
            raise RuntimeError(
                f"Existing model file {dest_path} is invalid and could not "
                f"be removed for re-download: {e}"
            ) from e

    try:
        dest_path.parent.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        logger.error(f"Cannot create model directory {dest_path.parent}: {e}")
        raise RuntimeError(f"Cannot create model directory: {e}") from e

    import requests

    # Download to a .part sibling and only atomically rename to dest_path
    # once the write is verified complete. dest_path.exists() above is what
    # future runs trust to mean "already have this" - if a partial write
    # ever reached dest_path directly, an interruption that no Python
    # exception handler can catch (process killed, power loss, a hard
    # crash - none of these run the except blocks below) would leave a
    # truncated file there, and the next run would skip re-downloading it,
    # treating corrupt data as complete. A temp path plus atomic rename
    # means dest_path only ever exists in its final, complete form.
    part_path = dest_path.with_name(dest_path.name + ".part")

    last_error: Optional[Exception] = None
    for attempt in range(1, max_attempts + 1):
        if attempt > 1:
            logger.info(f"Retrying download of {label} (attempt {attempt}/{max_attempts})...")
            time.sleep(1.5 * attempt)
        logger.info(f"Downloading {label} from {url} ...")
        try:
            resp = requests.get(url, stream=True, timeout=60)
            resp.raise_for_status()
            total = int(resp.headers.get("content-length", 0))
            downloaded = 0
            last_reported_pct = -1

            def _write_all(pbar=None):
                nonlocal downloaded, last_reported_pct
                with open(part_path, "wb") as fh:
                    for chunk in resp.iter_content(chunk_size=65536):
                        if not chunk:
                            continue
                        fh.write(chunk)
                        downloaded += len(chunk)
                        if pbar is not None:
                            pbar.update(len(chunk))
                        if progress_callback:
                            # Throttle to whole-percent (or every chunk if size unknown)
                            # so we don't flood the caller with thousands of updates.
                            pct = int(downloaded * 100 / total) if total > 0 else -1
                            if total <= 0 or pct != last_reported_pct:
                                last_reported_pct = pct
                                progress_callback(label, downloaded, total)

            if progress_callback:
                # Already have our own progress reporting (e.g. the TUI's status
                # bar) - skip tqdm's own terminal rendering entirely.
                _write_all()
            else:
                from tqdm import tqdm
                with tqdm(
                    total=total if total > 0 else None,
                    unit="B",
                    unit_scale=True,
                    desc=f"Downloading {label}"
                ) as pbar:
                    _write_all(pbar)

            # Verify against the server's declared size before trusting the
            # download - a connection that drops mid-stream without raising
            # (some servers/proxies just close silently) would otherwise
            # produce a short-but-not-exception-raising write.
            if total > 0 and downloaded != total:
                raise IOError(
                    f"Downloaded size ({downloaded} bytes) does not match "
                    f"expected size ({total} bytes) - connection likely "
                    f"dropped mid-download"
                )

            # Verify the download is actually a GGUF model before promoting
            # it to the final path. A URL that returned an HTML error page,
            # a login/consent wall, or a redirect body would otherwise pass
            # the size check above and be atomically saved as a valid-looking
            # .gguf - then fail deep inside llama.cpp at load time. Catching
            # it here gives a clear, actionable error and leaves no bad file
            # behind (the .part is discarded, dest_path is never written).
            if not is_valid_gguf(part_path):
                try:
                    part_path.unlink()
                except OSError:
                    pass
                raise InvalidModelFileError(
                    f"{label}: downloaded file is not a valid GGUF model "
                    f"(the URL may point to an HTML page, a login wall, or "
                    f"a non-model file rather than a direct .gguf download)."
                )

            os.replace(part_path, dest_path)  # atomic on the same filesystem
            logger.info(f"{label}: saved to {dest_path}")
            if progress_callback:
                progress_callback(label, downloaded, total if total > 0 else downloaded)
            return

        except InvalidModelFileError as e:
            # Deterministic: the same URL returns the same non-model content
            # on every attempt, so retrying only re-downloads the same
            # garbage. Fail immediately with the clear message. Listed
            # before the requests/Exception handlers so it can never be
            # swallowed and retried by them.
            logger.error(str(e))
            if part_path.exists():
                part_path.unlink()
            raise
        except ImportError as e:
            logger.error(f"Missing dependency for model download: {e}")
            raise RuntimeError(f"Missing dependency: {e}. Install with: pip install requests tqdm") from e
        except requests.RequestException as e:
            response = getattr(e, "response", None)
            # The 403 happens on the URL requests was redirected TO (the
            # xethub/cas-bridge domain), not the original huggingface.co
            # resolve URL we requested - response.url reflects the final,
            # post-redirect URL, which is what must be checked here.
            failure_url = getattr(response, "url", None) or url
            is_xet_bridge_failure = (
                response is not None
                and response.status_code == 403
                and ("xethub" in failure_url or "cas-bridge" in failure_url)
            )
            if is_xet_bridge_failure and attempt < max_attempts:
                # HuggingFace's "Xet" storage backend routes legacy/plain
                # HTTP downloads through a CAS bridge (cas-bridge.xethub.hf.co)
                # that has a long-documented history of intermittent 403s,
                # independent of this project - confirmed by many unrelated
                # reports of the exact same failure over many months. Unlike
                # a real 404/401, this is worth retrying: each attempt gets a
                # freshly-signed URL, and the underlying issue is reported as
                # transient in many (not all) cases.
                logger.warning(
                    f"{label}: HuggingFace's Xet storage bridge returned 403 "
                    f"(attempt {attempt}/{max_attempts}) - this is a known, "
                    f"external HF infrastructure issue, not specific to this "
                    f"file or this app. Retrying with a fresh signed URL..."
                )
                last_error = e
                if part_path.exists():
                    part_path.unlink()
                continue
            # Real HTTP-level failure (404, 401, timeout, DNS, ...) - not
            # transient, retrying won't help. Also reached for the Xet CAS
            # bridge failure once retries are exhausted.
            logger.error(f"Failed to download {label}: {e}")
            if part_path.exists():
                part_path.unlink()
            if is_xet_bridge_failure:
                raise RuntimeError(
                    f"Download failed for {label}: HuggingFace's Xet storage "
                    f"bridge (cas-bridge.xethub.hf.co) returned 403 Forbidden "
                    f"after {max_attempts} attempts. This is a known, "
                    f"recurring issue on HuggingFace's side (search "
                    f"'cas-bridge.xethub.hf.co 403' - other users hit this "
                    f"intermittently across many months), not something "
                    f"wrong with this app or your connection. It typically "
                    f"resolves on its own within a few hours. Try again "
                    f"later, or download the file manually via a browser "
                    f"and place it directly in the models/ folder."
                ) from e
            raise RuntimeError(f"Download failed for {label}: {e}") from e
        except Exception as e:
            # Catches low-level, non-HTTP failures (e.g. the CPython/OS
            # 'bad value(s) in fds_to_keep' class of transient thread/subprocess
            # errors) which are typically momentary - worth a retry. Also
            # catches the size-mismatch IOError raised above.
            logger.error(f"Unexpected error downloading {label} (attempt {attempt}/{max_attempts}): {e}")
            last_error = e
            if part_path.exists():
                part_path.unlink()

    raise RuntimeError(f"Download failed after {max_attempts} attempts: {last_error}") from last_error


def download_model(
    model_key: str,
    cfg: Dict[str, Any],
    progress_callback: Optional[ProgressCallback] = None,
) -> None:
    model_path = MODEL_DIR / cfg["file"]
    _stream_download(model_key, cfg["url"], model_path, progress_callback=progress_callback)


def filename_from_url(url: str) -> str:
    """Derive a safe local filename from a download URL."""
    name = url.rstrip("/").rsplit("/", 1)[-1].split("?", 1)[0]
    name = re.sub(r"[^A-Za-z0-9._-]", "_", name) or "custom-model.gguf"
    if not name.lower().endswith(".gguf"):
        name += ".gguf"
    return name


def download_custom_model(
    url: str,
    filename: Optional[str] = None,
    progress_callback: Optional[ProgressCallback] = None,
) -> Path:
    """Download an arbitrary .gguf URL (e.g. a HuggingFace 'resolve/main/...' link)
    into MODEL_DIR. Returns the path the model was saved to."""
    url = url.strip()
    if not url:
        raise ValueError("No URL provided.")
    if not url.lower().startswith(("http://", "https://")):
        raise ValueError("URL must start with http:// or https://")
    if url.lower().startswith("http://"):
        # Plain HTTP is permitted (some users have legitimate internal
        # model mirrors that aren't served over TLS), but it's worth a
        # warning: an on-path attacker could tamper with the file in
        # transit. The GGUF header check on completion limits the blast
        # radius to a file that at least looks like a model, but it can't
        # detect a malicious-but-well-formed substitute - prefer https://
        # when the source offers it.
        logger.warning(
            "Downloading over plain HTTP (not HTTPS): the file could be "
            "tampered with in transit. Prefer an https:// URL if the source "
            "offers one."
        )

    name = filename.strip() if filename else filename_from_url(url)
    dest_path = MODEL_DIR / name
    _stream_download(name, url, dest_path, progress_callback=progress_callback)
    return dest_path


def main(progress_callback: Optional[ProgressCallback] = None) -> Dict[str, Any]:
    """Download all configured preset models.
    Returns {model_key: {"success": bool, "error": Optional[str]}} for each.
    """
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )
    results: Dict[str, Any] = {}
    for key, cfg in MODELS_CONFIG.items():
        try:
            download_model(key, cfg, progress_callback=progress_callback)
            results[key] = {"success": True, "error": None}
        except Exception as e:
            logger.error(f"Failed to download {key}: {e}")
            results[key] = {"success": False, "error": str(e)}
    return results


if __name__ == "__main__":
    main()