"""LLM-based refinement backend using llama-cpp-python."""

import gc
import logging
import re
import threading
from pathlib import Path
from typing import Any, Dict, Optional

from ..backends import ModelBackend

logger = logging.getLogger(__name__)


class LLMBasedBackend(ModelBackend):
    """LLM-based refinement using a local llama.cpp model."""

    def __init__(self, model_path: Optional[Path] = None):
        if model_path is None:
            model_path = self._discover_default_model()
        self.model_path = Path(model_path) if model_path else None
        self.llm = None
        self.last_error: Optional[str] = None
        self._model_loaded = False
        self._lock = threading.RLock()

    @staticmethod
    def _discover_default_model() -> Optional[Path]:
        try:
            from ..config import ConfigManager
            from ...utils.path_utils import get_project_root

            config = ConfigManager(get_project_root(__file__) / "config.yaml")
            configured = config.get("llm.model_path")
            if configured:
                configured_path = Path(configured)
                if configured_path.exists():
                    return configured_path
                logger.warning("Configured LLM model path does not exist")
        except Exception as exc:
            logger.debug("Could not read configured model path (%s)", type(exc).__name__)

        try:
            from ...utils.system_utils import MODEL_DIR

            if MODEL_DIR.exists():
                candidates = sorted(MODEL_DIR.glob("*.gguf"))
                if candidates:
                    return candidates[0]
        except Exception as exc:
            logger.debug("Could not auto-discover a model (%s)", type(exc).__name__)
        return None

    def _validate_model_path(self, path: Path) -> bool:
        if path.is_symlink() or not path.is_file():
            return False
        if path.suffix.lower() != ".gguf":
            logger.warning("Configured model has an unexpected extension")
            return False
        try:
            if path.stat().st_size < 100_000_000:
                logger.warning("Configured model file is too small")
                return False
            with path.open("rb") as handle:
                if handle.read(4) != b"GGUF":
                    logger.warning("Configured model has an invalid GGUF header")
                    return False
        except OSError as exc:
            logger.warning("Could not validate model file (%s)", type(exc).__name__)
            return False
        return True

    @staticmethod
    def _is_memory_error(exc: BaseException) -> bool:
        if isinstance(exc, MemoryError):
            return True
        message = str(exc).lower()
        markers = (
            "out of memory",
            "cannot allocate memory",
            "failed to allocate",
            "memory allocation",
            "cuda error out of memory",
            "metal buffer",
        )
        return any(marker in message for marker in markers)

    def _load_model(self) -> bool:
        with self._lock:
            if self.llm is not None:
                return True
            if self.model_path is None:
                self.last_error = "No model path configured"
                return False
            if not self._validate_model_path(self.model_path):
                self.last_error = "Configured model file is missing, unsafe, or invalid"
                return False
            try:
                from llama_cpp import Llama
            except ImportError as exc:
                self.last_error = (
                    'llama-cpp-python is not installed. Run: pip install -e ".[llm]" '
                    "(from the project root)"
                )
                raise RuntimeError(self.last_error) from exc

            try:
                chat_format = self._validate_chat_format(self._detect_chat_format())
                candidate = Llama(
                    model_path=str(self.model_path),
                    n_ctx=4096,
                    n_threads=None,
                    n_batch=512,
                    chat_format=chat_format,
                    verbose=False,
                )
            except Exception as exc:
                self.llm = None
                self._model_loaded = False
                if self._is_memory_error(exc):
                    self.last_error = (
                        "Not enough available memory to load the selected model. "
                        "Close other applications or choose a smaller GGUF model."
                    )
                    logger.warning("LLM model load failed due to insufficient memory")
                else:
                    self.last_error = "The local LLM model could not be loaded"
                    logger.warning("LLM model load failed (%s)", type(exc).__name__)
                gc.collect()
                return False

            self.llm = candidate
            self._model_loaded = True
            self.last_error = None
            logger.info(
                "Local LLM model loaded (file=%s, chat_format=%s)",
                self.model_path.name,
                chat_format or "auto",
            )
            return True

    @staticmethod
    def _validate_chat_format(name: Optional[str]) -> Optional[str]:
        if name is None:
            return None
        try:
            from llama_cpp.llama_chat_format import get_chat_completion_handler

            get_chat_completion_handler(name)
            return name
        except Exception as exc:
            logger.warning(
                "Requested chat format is unavailable (%s); using GGUF auto-detection",
                type(exc).__name__,
            )
            return None

    def _detect_chat_format(self) -> Optional[str]:
        if self.model_path is None:
            return None
        name = self.model_path.name.lower()
        if any(marker in name for marker in ("phi-4", "phi4", "phi-3", "phi3")):
            return "phi3"
        if "tinyllama" in name or "zephyr" in name:
            return "zephyr"
        return None

    def _ensure_model_loaded(self) -> bool:
        if self.llm is not None:
            return True
        return self._load_model()

    def refine(
        self,
        prompt: str,
        profile: Dict[str, Any],
        polish_mode: bool = False,
    ) -> Optional[str]:
        with self._lock:
            if not self._ensure_model_loaded() or self.llm is None:
                logger.warning("LLM refinement unavailable")
                return None

            system_prompt = self._build_system_prompt(profile, polish_mode=polish_mode)
            user_content = f"Request: {prompt}"
            if self._is_thinking_model():
                user_content += " /no_think"

            try:
                output = self.llm.create_chat_completion(
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_content},
                    ],
                    max_tokens=512,
                    stop=["</s>", "<|im_end|>", "<|end|>", "<|user|>", "Request:"],
                    temperature=0.1,
                )
                if isinstance(output, dict) and output.get("choices"):
                    message = output["choices"][0].get("message", {})
                    result = (message.get("content") or "").strip()
                else:
                    result = str(output).strip()
            except Exception as exc:
                if self._is_memory_error(exc):
                    self.last_error = (
                        "The local model ran out of memory during refinement. "
                        "The model was unloaded so PromptSmith can continue."
                    )
                    logger.warning("LLM refinement stopped due to insufficient memory")
                    self.unload()
                else:
                    self.last_error = "The local model failed to refine the prompt"
                    logger.warning("LLM refinement failed (%s)", type(exc).__name__)
                return None

            result = self._strip_think_blocks(result)
            if not result:
                self.last_error = "Model output contained no usable answer after reasoning was removed"
                logger.warning("LLM returned no usable answer")
                return None

            result = self._take_first_complete_section(self._strip_preamble(result))
            if not result:
                self.last_error = "The local model returned an empty refinement"
                logger.warning("LLM returned an empty refinement")
                return None

            self.last_error = None
            logger.debug("LLM refinement completed (characters=%d)", len(result))
            return result

    def _is_thinking_model(self) -> bool:
        if self.model_path is None:
            return False
        name = self.model_path.name.lower()
        return any(
            marker in name
            for marker in ("qwen3", "qwq", "deepseek-r1", "r1-distill")
        )

    @staticmethod
    def _strip_think_blocks(text: str) -> str:
        if not text:
            return text
        if "<think>" in text and "</think>" not in text:
            return ""
        return re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()

    @staticmethod
    def _strip_preamble(text: str) -> str:
        if not text:
            return text
        patterns = [
            r"^(improved|refined|revised|updated|final|polished|rewritten)\s+"
            r"(prompt|request)\s*:\s*",
            r"^here('s| is)\s+(the\s+)?"
            r"(improved|refined|revised|polished|rewritten)\s+"
            r"(prompt|request)\s*:?\s*",
        ]
        stripped = text.strip()
        for pattern in patterns:
            stripped = re.sub(pattern, "", stripped, flags=re.IGNORECASE).strip()
        return stripped

    @staticmethod
    def _take_first_complete_section(text: str) -> str:
        if not text:
            return text
        pattern = re.compile(
            r"\n\s*(rewritten|improved|refined|revised|updated|final|polished)\s+"
            r"(prompt|request)\s*:\s*",
            re.IGNORECASE,
        )
        match = pattern.search(text)
        if match and match.start() > 20:
            return text[: match.start()].strip()
        return text

    def _build_system_prompt(
        self,
        profile: Dict[str, Any],
        polish_mode: bool = False,
    ) -> str:
        role = profile.get("role", "user")
        domain = ", ".join(profile.get("domain", []))
        tone = profile.get("tone", "neutral")
        fmt = profile.get("format", "text")

        if polish_mode:
            return (
                f"You are a prompt-editing assistant. The request below is already "
                f"fully specified for a {role}. Rewrite it into clearer prose without "
                f"dropping, weakening, or adding requirements. Domain: "
                f"{domain or 'general'}. Tone: {tone}. Output format: {fmt}. "
                f"Return only the rewritten request."
            )
        return (
            f"You are a prompt-editing assistant. Rewrite the request so it is clearer "
            f"and more detailed for a {role}. Do not answer or perform the request. "
            f"Domain: {domain or 'general'}. Tone: {tone}. Output format: {fmt}. "
            f"Return only the rewritten request."
        )

    def unload(self) -> None:
        with self._lock:
            model = self.llm
            self.llm = None
            self._model_loaded = False
            if model is None:
                return
            try:
                close = getattr(model, "close", None)
                if callable(close):
                    close()
            except Exception as exc:
                logger.warning("LLM cleanup reported an error (%s)", type(exc).__name__)
            finally:
                del model
                gc.collect()
                logger.info("Local LLM model unloaded")

    def __del__(self):
        try:
            self.unload()
        except Exception:
            pass
