"""Optional keyless local generation for the ATLAS RAG response path.

The model is warmed in the background during FastAPI startup. Dashboard and
Stats remain immediately available, while Chat falls back to grounded retrieval
until the model is fully loaded. Gemini remains preferred when configured.
"""

from __future__ import annotations

from concurrent.futures import Future, ThreadPoolExecutor, TimeoutError
import logging
import os
from pathlib import Path
from threading import RLock, Thread
from time import monotonic
from typing import Any


DEFAULT_MODEL = "Qwen/Qwen2.5-1.5B-Instruct"
# Uvicorn configures this logger at INFO level, so warm-up lifecycle messages
# are visible in the deployment terminal without custom logging setup.
logger = logging.getLogger("uvicorn.error")


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
        self.max_new_tokens = min(int(os.getenv("ATLAS_LOCAL_LLM_MAX_NEW_TOKENS", "64")), 96)
        self.timeout_seconds = float(os.getenv("ATLAS_LOCAL_LLM_TIMEOUT_SECONDS", "11"))
        self.interactive_timeout_seconds = min(
            self.timeout_seconds,
            # Keep the documented 11-second generation ceiling. While the
            # warm-up thread is loading, requests never enter this path and
            # return the deterministic grounded answer immediately.
            float(os.getenv("ATLAS_LOCAL_LLM_INTERACTIVE_TIMEOUT_SECONDS", "11")),
        )
        legacy_local_only = os.getenv("ATLAS_LOCAL_LLM_LOCAL_FILES_ONLY")
        self.local_files_only = (
            legacy_local_only.casefold() in {"1", "true", "yes"}
            if legacy_local_only is not None
            # The primary runtime starts this download in its background
            # warm-up thread. Set ATLAS_LOCAL_LLM_ALLOW_DOWNLOAD=false to run
            # strictly from a pre-seeded cache in a locked-down deployment.
            else not _is_enabled("ATLAS_LOCAL_LLM_ALLOW_DOWNLOAD", True)
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
        logger.info(
            "ATLAS local LLM loading in background: model=%s local_files_only=%s",
            self.model_id,
            self.local_files_only,
        )
        if self.local_files_only and not self._has_cached_model_snapshot():
            with self._lock:
                self._state = "unavailable"
                self._error = "The configured local model is not cached; using deterministic grounded synthesis."
            logger.warning("ATLAS local LLM unavailable: %s", self._error)
            return False
        try:
            self._clear_interrupted_cache_artifacts()
            import torch
            from transformers import AutoModelForCausalLM, AutoTokenizer

            # Hosted workspaces can default PyTorch to fewer threads than the
            # allocated vCPUs. Use a bounded, overridable setting so the local
            # 1.5B model can meet its protected interactive budget on CPU.
            cpu_threads = max(1, int(os.getenv("ATLAS_LOCAL_LLM_CPU_THREADS", str(os.cpu_count() or 1))))
            torch.set_num_threads(cpu_threads)

            tokenizer = AutoTokenizer.from_pretrained(self.model_id, local_files_only=self.local_files_only)
            model_kwargs: dict[str, Any] = {
                "local_files_only": self.local_files_only,
                # Avoid a second full checkpoint copy while loading the 1.5B
                # model. `accelerate` is optional at runtime; if this load
                # fails, the existing deterministic answer path remains safe.
                "low_cpu_mem_usage": True,
            }
            if torch.cuda.is_available():
                model_kwargs.update({"dtype": torch.bfloat16, "device_map": "auto"})
            else:
                # This runtime exposes AVX512/BF16 support. bfloat16 reduces
                # the 1.5B model's memory footprint and CPU inference cost;
                # deployments can set ATLAS_LOCAL_LLM_CPU_DTYPE=float32 if
                # their processor/runtime does not support it.
                cpu_dtype = os.getenv("ATLAS_LOCAL_LLM_CPU_DTYPE", "bfloat16").casefold()
                model_kwargs["dtype"] = torch.float32 if cpu_dtype == "float32" else torch.bfloat16
            model = AutoModelForCausalLM.from_pretrained(self.model_id, **model_kwargs)
            model.eval()
            with self._lock:
                self._tokenizer = tokenizer
                self._model = model
                self._torch = torch
                self._state = "ready"
                self._error = ""
            logger.info("ATLAS local LLM ready: model=%s", self.model_id)
            return True
        except Exception as error:  # pragma: no cover - dependent on local model/cache/runtime
            with self._lock:
                self._state = "unavailable"
                self._error = f"{type(error).__name__}: {error}"[:300]
            logger.warning("ATLAS local LLM warm-up failed; grounded fallback remains active: %s", self._error)
            return False

    def warm_up(self) -> None:
        """Download/load weights off the request path without blocking Chat."""

        if not self.enabled or self._state != "not_loaded":
            return
        logger.info("ATLAS local LLM warm-up scheduled: model=%s", self.model_id)
        Thread(target=self._load, name="atlas-local-llm-warmup", daemon=True).start()

    def _generate_with_model(self, prompt: str, remaining_seconds: float) -> str | None:
        """Run one model call; the caller owns the request-facing time budget."""

        try:
            messages = [
                {
                    "role": "system",
                    "content": (
                        "You are ATLAS, a senior SAP support lead. Answer only the user's question using the supplied enterprise evidence. "
                        "Reply in the same language as the user. Use concise natural paragraphs and short numbered actions when useful. Mention a ticket number only when it is relevant. "
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
            # Reserve a small portion of the request budget for framework
            # scheduling and token decoding. Without this, `generate(max_time
            # = remaining_seconds)` races the outer Future timeout and a valid
            # answer can be discarded at the exact deadline.
            generation_budget = max(0.2, remaining_seconds - 0.5)
            self._generation_future = self._generation_executor.submit(
                self._generate_with_model,
                prompt,
                generation_budget,
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
