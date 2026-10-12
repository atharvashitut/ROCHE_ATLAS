"""Optional keyless local generation for the ATLAS RAG response path.

The model is intentionally lazy-loaded.  Starting the FastAPI service or
viewing Dashboard/Stats never downloads a model; the first eligible Chat query
does.  Gemini remains the preferred provider whenever its client is configured.
"""

from __future__ import annotations

from concurrent.futures import Future, ThreadPoolExecutor, TimeoutError
import os
from pathlib import Path
from threading import RLock, Thread
from time import monotonic
from typing import Any


DEFAULT_MODEL = "Qwen/Qwen2.5-0.5B-Instruct"


def _is_enabled(name: str, default: bool) -> bool:
    value = os.getenv(name)
    return default if value is None else value.casefold() in {"1", "true", "yes", "on"}


def _hub_cache_root() -> Path:
    """Resolve Hugging Face's hub cache without assuming a particular home path."""

    if cache_path := os.getenv("HF_HUB_CACHE"):
        return Path(cache_path)
    if hf_home := os.getenv("HF_HOME"):
        return Path(hf_home) / "hub"
    if xdg_cache := os.getenv("XDG_CACHE_HOME"):
        return Path(xdg_cache) / "huggingface" / "hub"
    return Path.home() / ".cache" / "huggingface" / "hub"


class LocalOpenSourceGenerator:
    """Hugging Face local-inference adapter with safe unavailable states."""

    def __init__(self) -> None:
        self.model_id = os.getenv("ATLAS_LOCAL_LLM_MODEL", DEFAULT_MODEL)
        self.enabled = os.getenv("ATLAS_LOCAL_LLM_ENABLED", "true").casefold() not in {"0", "false", "no"}
        self.max_new_tokens = min(int(os.getenv("ATLAS_LOCAL_LLM_MAX_NEW_TOKENS", "16")), 96)
        self.timeout_seconds = float(os.getenv("ATLAS_LOCAL_LLM_TIMEOUT_SECONDS", "11"))
        self.interactive_timeout_seconds = min(
            self.timeout_seconds,
            float(os.getenv("ATLAS_LOCAL_LLM_INTERACTIVE_TIMEOUT_SECONDS", "2.8")),
        )
        legacy_local_only = os.getenv("ATLAS_LOCAL_LLM_LOCAL_FILES_ONLY")
        self.local_files_only = (
            legacy_local_only.casefold() in {"1", "true", "yes"}
            if legacy_local_only is not None
            else not _is_enabled("ATLAS_LOCAL_LLM_ALLOW_DOWNLOAD", False)
        )
        self._lock = RLock()
        self._model: Any | None = None
        self._tokenizer: Any | None = None
        self._torch: Any | None = None
        self._generation_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="atlas-local-llm")
        self._generation_future: Future[str | None] | None = None
        self._state = "not_loaded" if self.enabled else "disabled"
        self._error = ""

    def _clear_interrupted_cache_artifacts(self) -> int:
        """Remove only stale partial files/locks for this model, never the shared cache."""

        model_cache_name = f"models--{self.model_id.replace('/', '--')}"
        hub_root = _hub_cache_root()
        targets = (hub_root / model_cache_name, hub_root / ".locks" / model_cache_name)
        removed = 0
        for target in targets:
            if not target.exists():
                continue
            pattern = "*.incomplete" if target.parent.name != ".locks" else "*.lock"
            for artifact in target.rglob(pattern):
                try:
                    artifact.unlink()
                    removed += 1
                except OSError:
                    continue
        return removed

    def _has_cached_model_snapshot(self) -> bool:
        """Avoid importing the inference runtime when a local-only model is absent."""

        model_cache_name = f"models--{self.model_id.replace('/', '--')}"
        snapshots = _hub_cache_root() / model_cache_name / "snapshots"
        return snapshots.is_dir() and any(snapshots.iterdir())

    def _load(self) -> bool:
        """Load the requested model once, without making import availability fatal."""

        if not self.enabled:
            return False
        with self._lock:
            if self._state == "ready":
                return True
            if self._state in {"loading", "unavailable"}:
                return False
            self._state = "loading"
        if self.local_files_only and not self._has_cached_model_snapshot():
            with self._lock:
                self._state = "unavailable"
                self._error = "The configured local model is not cached; using deterministic grounded synthesis."
            return False
        try:
            self._clear_interrupted_cache_artifacts()
            import torch
            from transformers import AutoModelForCausalLM, AutoTokenizer

            tokenizer = AutoTokenizer.from_pretrained(self.model_id, local_files_only=self.local_files_only)
            model_kwargs: dict[str, Any] = {"local_files_only": self.local_files_only}
            if torch.cuda.is_available():
                model_kwargs.update({"dtype": torch.bfloat16, "device_map": "auto"})
            else:
                model_kwargs["dtype"] = torch.float32
            model = AutoModelForCausalLM.from_pretrained(self.model_id, **model_kwargs)
            model.eval()
            with self._lock:
                self._tokenizer = tokenizer
                self._model = model
                self._torch = torch
                self._state = "ready"
                self._error = ""
            return True
        except Exception as error:  # pragma: no cover - dependent on local model/cache/runtime
            with self._lock:
                self._state = "unavailable"
                self._error = f"{type(error).__name__}: {error}"[:300]
            return False

    def warm_up(self) -> None:
        """Load cached local weights off the request path; missing files fail fast."""

        if not self.enabled or self._state != "not_loaded":
            return
        Thread(target=self._load, name="atlas-local-llm-warmup", daemon=True).start()

    def _generate_with_model(self, prompt: str, remaining_seconds: float) -> str | None:
        """Run one model call; the caller owns the request-facing time budget."""

        try:
            messages = [
                {
                    "role": "system",
                    "content": (
                        "You are ATLAS, a senior SAP support lead. Answer only the user's question using the supplied enterprise evidence. "
                        "Use concise natural paragraphs and short numbered actions when useful. Mention a ticket number only when it is relevant. "
                        "Do not output JSON, source IDs, URLs, debug metadata, full journals, topology, or ticket drawers. "
                        "If you use a document, refer to its title naturally in a sentence. Do not invent facts outside the evidence."
                    ),
                },
                {"role": "user", "content": prompt},
            ]
            model_inputs = self._tokenizer.apply_chat_template(
                messages,
                tokenize=True,
                add_generation_prompt=True,
                return_tensors="pt",
                return_dict=True,
            )
            device = next(self._model.parameters()).device
            model_inputs = {key: value.to(device) for key, value in model_inputs.items()}
            with self._torch.inference_mode():
                output = self._model.generate(
                    **model_inputs,
                    max_new_tokens=self.max_new_tokens,
                    max_time=remaining_seconds,
                    do_sample=False,
                    pad_token_id=self._tokenizer.eos_token_id,
                )
            generated_tokens = output[0][model_inputs["input_ids"].shape[-1]:]
            answer = self._tokenizer.decode(generated_tokens, skip_special_tokens=True).strip()
            return answer or None
        except Exception as error:  # pragma: no cover - dependent on model/runtime capacity
            self._error = f"{type(error).__name__}: {error}"[:300]
            return None

    def generate(self, prompt: str) -> str | None:
        """Generate within the 11-second ceiling and a shorter interactive budget."""

        started_at = monotonic()
        if not self._load() or self._model is None or self._tokenizer is None or self._torch is None:
            return None
        remaining_seconds = self.interactive_timeout_seconds - (monotonic() - started_at)
        if remaining_seconds <= 0:
            self._error = f"Local model load exceeded the {self.interactive_timeout_seconds:g}-second interactive response budget."
            return None
        with self._lock:
            if self._generation_future is not None and not self._generation_future.done():
                self._error = "Local generation is still completing a prior request; using instant grounded synthesis."
                return None
            self._generation_future = self._generation_executor.submit(
                self._generate_with_model,
                prompt,
                remaining_seconds,
            )
            generation = self._generation_future
        try:
            return generation.result(timeout=remaining_seconds)
        except TimeoutError:
            self._error = f"Local generation exceeded the {self.interactive_timeout_seconds:g}-second interactive response budget."
            return None

    def status(self) -> dict[str, object]:
        """Expose readiness without leaking a model prompt or credential."""

        return {
            "provider": "Hugging Face local inference",
            "model": self.model_id,
            "enabled": self.enabled,
            "state": self._state,
            "local_files_only": self.local_files_only,
            "timeout_seconds": self.timeout_seconds,
            "interactive_timeout_seconds": self.interactive_timeout_seconds,
            "max_new_tokens": self.max_new_tokens,
            "generation_busy": self._generation_future is not None and not self._generation_future.done(),
            "error": self._error or None,
        }


LOCAL_OPEN_SOURCE_GENERATOR = LocalOpenSourceGenerator()
