"""Optional keyless local generation for the ATLAS RAG response path.

The model is intentionally lazy-loaded.  Starting the FastAPI service or
viewing Dashboard/Stats never downloads a model; the first eligible Chat query
does.  Gemini remains the preferred provider whenever its client is configured.
"""

from __future__ import annotations

import os
from threading import RLock
from typing import Any


DEFAULT_MODEL = "Qwen/Qwen2.5-1.5B-Instruct"


class LocalOpenSourceGenerator:
    """Hugging Face local-inference adapter with safe unavailable states."""

    def __init__(self) -> None:
        self.model_id = os.getenv("ATLAS_LOCAL_LLM_MODEL", DEFAULT_MODEL)
        self.enabled = os.getenv("ATLAS_LOCAL_LLM_ENABLED", "true").casefold() not in {"0", "false", "no"}
        self.max_new_tokens = int(os.getenv("ATLAS_LOCAL_LLM_MAX_NEW_TOKENS", "420"))
        self.local_files_only = os.getenv("ATLAS_LOCAL_LLM_LOCAL_FILES_ONLY", "false").casefold() in {"1", "true", "yes"}
        self._lock = RLock()
        self._model: Any | None = None
        self._tokenizer: Any | None = None
        self._torch: Any | None = None
        self._state = "not_loaded" if self.enabled else "disabled"
        self._error = ""

    def _load(self) -> bool:
        """Load the requested model once, without making import availability fatal."""

        if not self.enabled:
            return False
        with self._lock:
            if self._state == "ready":
                return True
            if self._state == "unavailable":
                return False
            try:
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
                self._tokenizer = tokenizer
                self._model = model
                self._torch = torch
                self._state = "ready"
                self._error = ""
                return True
            except Exception as error:  # pragma: no cover - dependent on local model/cache/runtime
                self._state = "unavailable"
                self._error = f"{type(error).__name__}: {error}"[:300]
                return False

    def generate(self, prompt: str) -> str | None:
        """Generate a concise grounded answer, or ``None`` if local inference is unavailable."""

        if not self._load() or self._model is None or self._tokenizer is None or self._torch is None:
            return None
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
                    do_sample=False,
                    pad_token_id=self._tokenizer.eos_token_id,
                )
            generated_tokens = output[0][model_inputs["input_ids"].shape[-1]:]
            answer = self._tokenizer.decode(generated_tokens, skip_special_tokens=True).strip()
            return answer or None
        except Exception as error:  # pragma: no cover - dependent on model/runtime capacity
            self._state = "unavailable"
            self._error = f"{type(error).__name__}: {error}"[:300]
            return None

    def status(self) -> dict[str, object]:
        """Expose readiness without leaking a model prompt or credential."""

        return {
            "provider": "Hugging Face local inference",
            "model": self.model_id,
            "enabled": self.enabled,
            "state": self._state,
            "local_files_only": self.local_files_only,
            "error": self._error or None,
        }


LOCAL_OPEN_SOURCE_GENERATOR = LocalOpenSourceGenerator()
