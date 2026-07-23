"""
LLM-based refinement backend using llama-cpp-python.
"""

import logging
import re
from pathlib import Path
from typing import Any, Dict, Optional

from ..backends import ModelBackend

logger = logging.getLogger(__name__)


class LLMBasedBackend(ModelBackend):
    """LLM-based refinement using llama-cpp-python."""

    def __init__(self, model_path: Optional[Path] = None):
        if model_path is None:
            model_path = self._discover_default_model()
        self.model_path = Path(model_path) if model_path else None
        self.llm = None
        self.last_error: Optional[str] = None
        self._model_loaded = False

    @staticmethod
    def _discover_default_model() -> Optional[Path]:
        """Find a usable model when none was explicitly configured.

        Checks config's 'llm.model_path' first, then falls back to the first
        .gguf file found in MODEL_DIR (e.g. what 'Download LLM Models' saved).
        """
        try:
            from ..config import ConfigManager
            from ...utils.path_utils import get_project_root
            config = ConfigManager(get_project_root(__file__) / "config.yaml")
            configured = config.get("llm.model_path")
            if configured:
                configured_path = Path(configured)
                if configured_path.exists():
                    return configured_path
                logger.warning(f"Configured llm.model_path does not exist: {configured_path}")
        except Exception as e:
            logger.debug(f"Could not read configured model path: {e}")

        try:
            from ...utils.system_utils import MODEL_DIR
            if MODEL_DIR.exists():
                candidates = sorted(MODEL_DIR.glob("*.gguf"))
                if candidates:
                    return candidates[0]
        except Exception as e:
            logger.debug(f"Could not auto-discover a model in MODEL_DIR: {e}")

        return None

    def _validate_model_path(self, path: Path) -> bool:
        if not path.exists():
            return False
        if path.suffix.lower() != ".gguf":
            logger.warning(f"Model file {path} has unexpected extension: {path.suffix}")
            return False
        try:
            file_size = path.stat().st_size
            if file_size < 100_000_000:
                logger.warning(f"Model file {path} is too small ({file_size} bytes)")
                return False
        except OSError as e:
            logger.warning(f"Cannot check model file size: {e}")
            return False
        try:
            with open(path, "rb") as f:
                header = f.read(4)
                if header != b"GGUF":
                    logger.warning(f"Model file {path} has invalid GGUF header")
                    return False
        except OSError as e:
            logger.warning(f"Cannot read model file header: {e}")
            return False
        return True

    def _load_model(self) -> bool:
        if self.model_path is None:
            self.last_error = "No model path configured"
            logger.error(self.last_error)
            return False
        if not self.model_path.exists():
            self.last_error = f"Model file not found: {self.model_path}"
            logger.error(self.last_error)
            return False
        if not self._validate_model_path(self.model_path):
            self.last_error = f"Invalid model file: {self.model_path}"
            logger.error(self.last_error)
            return False
        try:
            from llama_cpp import Llama
        except ImportError as exc:
            self.last_error = "llama-cpp-python is not installed. Run: pip install -e \".[llm]\" (from the project root)"
            logger.error(self.last_error)
            raise RuntimeError(self.last_error) from exc
        try:
            chat_format = self._detect_chat_format()
            chat_format = self._validate_chat_format(chat_format)
            self.llm = Llama(
                model_path=str(self.model_path),
                n_ctx=4096,
                n_threads=None,
                n_batch=512,
                chat_format=chat_format,
                verbose=False,
            )
            self._model_loaded = True
            logger.info(
                f"Successfully loaded LLM model from {self.model_path} "
                f"(chat_format={chat_format or 'auto (from GGUF metadata)'})"
            )
            return True
        except Exception as exc:
            self.last_error = f"Failed to load LLM model: {exc}"
            logger.error(self.last_error)
            self.llm = None
            self._model_loaded = False
            raise RuntimeError(self.last_error) from exc

    @staticmethod
    def _validate_chat_format(name: Optional[str]) -> Optional[str]:
        """Confirm a chat_format name is actually registered in the
        installed llama-cpp-python version before using it. The set of
        built-in formats varies by version (e.g. 'phi3' isn't registered in
        some versions at all, and the error only surfaces later, lazily,
        when create_chat_completion() is called - not at Llama() construction
        time). Checking here avoids ever handing an invalid name to Llama(),
        falling back to None (auto-detect from the GGUF's own embedded chat
        template) instead."""
        if name is None:
            return None
        try:
            from llama_cpp.llama_chat_format import get_chat_completion_handler
            get_chat_completion_handler(name)
            return name
        except Exception as exc:
            logger.warning(
                f"chat_format={name!r} is not available in this llama-cpp-python "
                f"version ({exc}); falling back to auto-detection from the GGUF's "
                f"own embedded chat template"
            )
            return None

    def _detect_chat_format(self) -> Optional[str]:
        """Pick a llama-cpp-python built-in chat_format for known model
        families by filename. For anything else (e.g. a custom model
        downloaded via a URL), return None so llama-cpp-python auto-detects
        the chat template embedded in the GGUF's own metadata instead."""
        if self.model_path is None:
            return None
        name = self.model_path.name.lower()
        if "phi-4" in name or "phi4" in name or "phi-3" in name or "phi3" in name:
            return "phi3"
        if "tinyllama" in name or "zephyr" in name:
            return "zephyr"
        return None

    def _ensure_model_loaded(self) -> bool:
        if self.llm is not None:
            return True
        if self._model_loaded:
            return False
        if self.model_path is None:
            self.last_error = "No model path configured"
            logger.warning(self.last_error)
            return False
        try:
            return self._load_model()
        except Exception:
            return False

    def refine(self, prompt: str, profile: Dict[str, Any], polish_mode: bool = False) -> Optional[str]:
        if not self._ensure_model_loaded():
            logger.warning("LLM not loaded, cannot refine")
            return None
        if self.llm is None:
            logger.warning("LLM not loaded, cannot refine")
            return None
        system_prompt = self._build_system_prompt(profile, polish_mode=polish_mode)
        user_content = f"Request: {prompt}"
        if self._is_thinking_model():
            # Qwen3's documented control switch to skip its <think>...</think>
            # reasoning phase. PromptSmith-cli's job here is a short rewrite, not
            # deep reasoning, and thinking mode risks the fixed max_tokens
            # budget below being exhausted entirely on reasoning that never
            # reaches the actual answer (see _strip_think_blocks). This is a
            # Qwen-specific optimization to avoid that in the common case;
            # _strip_think_blocks is the general-purpose safety net for any
            # thinking-capable model, Qwen or otherwise.
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
            if isinstance(output, dict) and "choices" in output and len(output["choices"]) > 0:
                message = output["choices"][0].get("message", {})
                result = (message.get("content") or "").strip()
            else:
                result = str(output).strip()
            result = self._strip_think_blocks(result)
            if not result:
                self.last_error = (
                    "Model output was entirely (or only incompletely) a "
                    "<think> reasoning block with no usable answer after it - "
                    "likely truncated by max_tokens before reasoning finished"
                )
                logger.warning(self.last_error)
                return None
            result = self._strip_preamble(result)
            result = self._take_first_complete_section(result)
            if result:
                logger.debug(f"LLM refinement successful: {result[:100]}...")
                return result
            else:
                logger.warning("LLM returned empty result")
                return None
        except KeyError as exc:
            self.last_error = f"Unexpected LLM output format: {exc}"
            logger.warning(f"LLM refinement failed (format): {exc}")
            return None
        except Exception as exc:
            self.last_error = str(exc)
            logger.warning(f"LLM refinement failed: {exc}")
            return None

    def _is_thinking_model(self) -> bool:
        """Filename-based detection of model families known to emit
        <think>...</think> reasoning by default (Qwen3, QwQ, DeepSeek-R1
        and its distills). Best-effort only - a custom download via URL may
        not match any of these patterns, which is fine: _strip_think_blocks
        still protects against an unexpected <think> block regardless."""
        if self.model_path is None:
            return False
        name = self.model_path.name.lower()
        return any(marker in name for marker in ("qwen3", "qwq", "deepseek-r1", "r1-distill"))

    @staticmethod
    def _strip_think_blocks(text: str) -> str:
        """Remove <think>...</think> reasoning blocks some models (Qwen3,
        QwQ, DeepSeek-R1) emit before their actual answer.

        Critically, an *unclosed* <think> tag - opening tag present, no
        matching close - means generation was cut off by max_tokens while
        still reasoning, before ever producing the real answer. Observed in
        production: the model's entire 512-token budget was consumed by
        mid-sentence reasoning, so the caller received a long, plausible-
        looking piece of text with zero actual content. Length-based
        degenerate-output checks elsewhere don't catch this because the
        text isn't short - it just isn't an answer. Treating it as empty
        output here (rather than passing the raw reasoning through) lets
        the normal "LLM returned nothing usable" path handle it correctly,
        including HybridBackend falling back to the rule-based result.
        """
        if not text:
            return text
        if "<think>" in text and "</think>" not in text:
            return ""
        return re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()

    @staticmethod
    def _strip_preamble(text: str) -> str:
        """Strip common header/preamble lines a model may still emit despite
        instructions, e.g. 'Improved prompt:', 'Refined prompt:', 'Here is...'."""
        if not text:
            return text
        preamble_patterns = [
            r"^(improved|refined|revised|updated|final|polished|rewritten)\s+(prompt|request)\s*:\s*",
            r"^here('s| is)\s+(the\s+)?(improved|refined|revised|polished|rewritten)\s+(prompt|request)\s*:?\s*",
        ]
        stripped = text.strip()
        for pattern in preamble_patterns:
            new_stripped = re.sub(pattern, "", stripped, flags=re.IGNORECASE)
            if new_stripped != stripped:
                stripped = new_stripped.strip()
        return stripped

    @staticmethod
    def _take_first_complete_section(text: str) -> str:
        """Some models loop and generate multiple rewrite attempts in one
        completion, separated by header-like lines ('Rewritten prompt:',
        'Improved prompt:', ...) - observed directly in production as three
        concatenated attempts, with the last one truncated mid-sentence by
        max_tokens. Keep only the first complete section.

        Only triggers on a header appearing after real content (not at the
        very start), so a single legitimate leading header - already handled
        by _strip_preamble - can't be mistaken for a repeat and truncated."""
        if not text:
            return text
        pattern = re.compile(
            r"\n\s*(rewritten|improved|refined|revised|updated|final|polished)\s+(prompt|request)\s*:\s*",
            re.IGNORECASE,
        )
        match = pattern.search(text)
        if match and match.start() > 20:
            return text[:match.start()].strip()
        return text

    def _build_system_prompt(self, profile: Dict[str, Any], polish_mode: bool = False) -> str:
        role = profile.get("role", "user")
        domain = ", ".join(profile.get("domain", []))
        tone = profile.get("tone", "neutral")
        fmt = profile.get("format", "text")

        if polish_mode:
            return (
                f"You are a prompt-editing assistant. The request below is already "
                f"fully specified - it lists every requirement needed for a {role}. "
                f"Your ONLY job is to rewrite it into clearer, more natural prose. "
                f"You are NOT answering the request, solving it, or producing its output. "
                f"Do not write code, do not perform the task described.\n\n"
                f"CRITICAL: Do not drop, weaken, or omit ANY requirement, constraint, "
                f"or detail from the original text. Every bullet point and instruction "
                f"in the request must still be represented in your rewrite, even if "
                f"reworded. Do not add new requirements either - only reorganize and "
                f"clarify what's already there.\n\n"
                f"Domain: {domain or 'general'}. Tone: {tone}. Output format: {fmt}.\n"
                f"Return ONLY the rewritten text. No commentary. No explanations."
            )

        return (
            f"You are a prompt-editing assistant. Your ONLY job is to rewrite "
            f"the text of a REQUEST so it is clearer and more detailed for a {role}. "
            f"You are NOT answering the request, solving it, or producing its output. "
            f"Do not write code, do not write an essay, do not perform the task described - "
            f"only rewrite the sentence(s) describing the task.\n\n"
            f"Example:\n"
            f"Request: a login form\n"
            f"Rewritten request: Create a login form with email and password fields, "
            f"client-side validation, and a submit button that calls an authentication API.\n\n"
            f"Focus the rewrite on:\n"
            f"- Clarity and specificity.\n"
            f"- Domain: {domain or 'general'}.\n"
            f"- Tone: {tone}.\n"
            f"- Output format: {fmt}.\n"
            f"Return ONLY the rewritten request text. No code. No commentary. No explanations."
        )

    def unload(self) -> None:
        if self.llm is not None:
            try:
                del self.llm
                self.llm = None
                self._model_loaded = False
                logger.info("LLM model unloaded")
            except Exception as e:
                logger.error(f"Error unloading model: {e}")
                self.llm = None
                self._model_loaded = False

    def __del__(self):
        self.unload()