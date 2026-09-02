"""Local LLM access through Ollama. Master prompt sections 4, 5 and 8.

Two rules are enforced in code here rather than left to documentation:

  LOCAL ONLY (section 4)   OLLAMA_LOCAL_ONLY=true / ALLOW_OLLAMA_CLOUD=false.
                           A non-loopback URL is refused outright, so a
                           config typo cannot quietly start sending prompts
                           off the machine.

  APPROVED MODELS (section 8)
                           "It is a Qwen" is explicitly not a licence. A
                           specific model ID must be APPROVED in
                           LICENSE_REGISTRY.json before generate() will touch
                           it. Pulling weights and using weights are separate
                           decisions, and this is the second one.

stdlib urllib on purpose: adding a pip dependency to a machine that turned
out not to have Python at all is not a trade worth making for one POST.
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any

DEFAULT_URL = "http://localhost:11434"
LOOPBACK_HOSTS = {"localhost", "127.0.0.1", "::1", "[::1]"}


class OllamaUnavailable(RuntimeError):
    """The server did not answer. Not a crash - a finding."""


class NonLocalEndpointRefused(RuntimeError):
    """Section 4: local only means local only."""


class ModelNotApproved(RuntimeError):
    """Section 8: this specific model ID is not APPROVED in the registry."""


class ModelNotInstalled(RuntimeError):
    """The requested model is not present in the local Ollama inventory."""


class ModelDoesNotFit(RuntimeError):
    """The requested model cannot be loaded within this machine's RAM budget."""


@dataclass
class ModelInfo:
    name: str
    size_gb: float
    parameter_size: str = ""
    quantization: str = ""


class OllamaClient:
    def __init__(self, base_url: str = DEFAULT_URL, *, local_only: bool = True,
                 registry_path: Path | None = None, timeout: float = 30.0,
                 opener=None, state_path: Path | None = None):
        self.base_url = base_url.rstrip("/")
        self.local_only = local_only
        self.registry_path = registry_path
        self.timeout = timeout
        self.state_path = state_path
        # Injectable so the licence and local-only gates can be tested without
        # a running server.
        self._opener = opener or self._urlopen

        if local_only and not self._is_loopback(self.base_url):
            raise NonLocalEndpointRefused(
                f"{self.base_url} is not loopback, and policy ollama_local_only is set. "
                "Section 4: cloud models are not used."
            )

    @staticmethod
    def _is_loopback(url: str) -> bool:
        from urllib.parse import urlparse
        host = (urlparse(url).hostname or "").lower()
        return host in LOOPBACK_HOSTS

    # ---- transport -------------------------------------------------------

    def _urlopen(self, request: urllib.request.Request, timeout: float) -> bytes:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.read()

    def _get(self, path: str) -> dict[str, Any]:
        request = urllib.request.Request(f"{self.base_url}{path}", method="GET")
        try:
            return json.loads(self._opener(request, self.timeout) or b"{}")
        except (urllib.error.URLError, OSError, TimeoutError) as exc:
            raise OllamaUnavailable(f"GET {path} failed: {exc}") from exc

    def _post(self, path: str, payload: dict[str, Any], timeout: float | None = None) -> dict[str, Any]:
        body = json.dumps(payload).encode("utf-8")
        request = urllib.request.Request(
            f"{self.base_url}{path}", data=body, method="POST",
            headers={"Content-Type": "application/json"},
        )
        try:
            return json.loads(self._opener(request, timeout or self.timeout) or b"{}")
        except (urllib.error.URLError, OSError, TimeoutError) as exc:
            raise OllamaUnavailable(f"POST {path} failed: {exc}") from exc

    # ---- queries ---------------------------------------------------------

    def is_available(self) -> tuple[bool, str]:
        """(reachable, detail). Never raises - callers need a status, not a stack trace."""
        started = time.monotonic()
        try:
            self._get("/api/tags")
        except OllamaUnavailable as exc:
            return False, str(exc)
        elapsed_ms = int((time.monotonic() - started) * 1000)
        return True, f"responded in {elapsed_ms} ms"

    def list_models(self) -> list[ModelInfo]:
        data = self._get("/api/tags")
        models = []
        for entry in data.get("models") or []:
            details = entry.get("details") or {}
            models.append(ModelInfo(
                name=entry.get("name", ""),
                size_gb=round((entry.get("size") or 0) / (1024 ** 3), 2),
                parameter_size=details.get("parameter_size", ""),
                quantization=details.get("quantization_level", ""),
            ))
        return models

    # ---- active model ---------------------------------------------------

    def active_model(self) -> str | None:
        """Return the persisted model choice, if one has been made."""
        if not self.state_path or not self.state_path.is_file():
            return None
        state = json.loads(self.state_path.read_text(encoding="utf-8-sig"))
        model = state.get("active_ollama_model")
        return str(model) if model else None

    def use_model(self, model: str, hardware_profile: Any) -> None:
        """Validate and persist a model without ever pulling model weights.

        Installation, licensing, and loadability are independent gates. All
        three pass before the state file is touched, so a refused change leaves
        the previous working choice intact.
        """
        # Keep the single authoritative licence decision in require_approved().
        try:
            self.require_approved(model)
        except ModelNotApproved as exc:
            raise ModelNotApproved(f"licence check failed: {exc}") from exc

        installed = {entry.name: entry for entry in self.list_models()}
        if model not in installed:
            raise ModelNotInstalled(
                f"installation check failed: '{model}' is not installed in Ollama"
            )

        recorded_sizes = dict(hardware_profile.ollama_model_sizes)
        size_gb = recorded_sizes.get(model, installed[model].size_gb)
        fit, why = hardware_profile.model_fit(size_gb)
        if fit not in ("VIABLE", "LIMITED"):
            raise ModelDoesNotFit(
                f"RAM fit check failed for '{model}': model size {size_gb:.2f} GB, "
                f"machine total {hardware_profile.ram_total_gb:.2f} GB. {why}"
            )

        if not self.state_path:
            raise ValueError("a state_path is required to persist the active Ollama model")
        state = {}
        if self.state_path.is_file():
            state = json.loads(self.state_path.read_text(encoding="utf-8-sig"))
        state["active_ollama_model"] = model
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        self.state_path.write_text(
            json.dumps(state, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )

    # ---- licence gate ----------------------------------------------------

    def approved_models(self) -> set[str]:
        """Model IDs marked APPROVED in the licence registry."""
        if not self.registry_path or not self.registry_path.is_file():
            return set()

        registry = json.loads(self.registry_path.read_text(encoding="utf-8-sig"))
        approved = set()
        for entry in registry.get("entries", []):
            if entry.get("type") == "ai_model" and entry.get("status") == "APPROVED":
                approved.add(entry.get("id", ""))
                for alias in entry.get("model_ids", []) or []:
                    approved.add(alias)
        return {name for name in approved if name}

    def require_approved(self, model: str) -> None:
        approved = self.approved_models()
        if model in approved:
            return

        if not approved:
            raise ModelNotApproved(
                f"No AI model is APPROVED in the licence registry yet, so '{model}' "
                "cannot be used. Section 8: verify this exact model ID's licence and "
                "add it with type 'ai_model' and status APPROVED first. Belonging to a "
                "family (Qwen, DeepSeek) is explicitly not sufficient."
            )
        raise ModelNotApproved(
            f"'{model}' is not APPROVED. Approved model IDs: {sorted(approved)}"
        )

    # ---- generation ------------------------------------------------------

    def generate(self, model: str, prompt: str, *, timeout: float | None = None,
                 options: dict[str, Any] | None = None) -> str:
        """One-shot completion. Refuses an unapproved model before any request."""
        self.require_approved(model)

        payload: dict[str, Any] = {"model": model, "prompt": prompt, "stream": False}
        if options:
            payload["options"] = options

        # Generous default: this machine has no dedicated GPU, so CPU inference
        # on even a 3B model is slow. A 30 s timeout would fail honest work.
        data = self._post("/api/generate", payload, timeout=timeout or 300.0)
        return data.get("response", "")

    def status_summary(self) -> str:
        reachable, detail = self.is_available()
        if not reachable:
            return f"Ollama UNREACHABLE at {self.base_url} - {detail}"

        try:
            models = self.list_models()
        except OllamaUnavailable as exc:
            return f"Ollama reachable but /api/tags failed: {exc}"

        if not models:
            return (
                f"Ollama reachable at {self.base_url} ({detail}) but NO models installed. "
                "Nothing can run until a model ID is licence-checked, APPROVED in "
                "LICENSE_REGISTRY.json, and pulled."
            )

        approved = self.approved_models()
        lines = [f"Ollama reachable at {self.base_url} ({detail})"]
        for model in models:
            mark = "APPROVED" if model.name in approved else "NOT APPROVED"
            lines.append(
                f"  {model.name}  {model.size_gb} GB  {model.parameter_size} "
                f"{model.quantization}  [{mark}]"
            )
        return "\n".join(lines)
