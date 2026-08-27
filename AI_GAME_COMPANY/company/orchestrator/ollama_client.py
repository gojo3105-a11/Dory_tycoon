"""Ollama gateway, stdlib only (master prompt section 4).

Local-only by policy: a non-localhost endpoint raises PaidActionBlocked rather
than quietly calling a hosted model. Not running is a normal, reportable state
(NOT_RUNNING), never an exception that stops the pipeline.
"""
from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from . import logging_setup, paths
from .policy import PaidActionBlocked, Policy

log = logging_setup.get_logger("ollama_client", quiet=True)

OK = "OK"
NOT_RUNNING = "NOT_RUNNING"
NO_MODELS = "NO_MODELS"
BLOCKED = "BLOCKED"
ERROR = "ERROR"


@dataclass
class OllamaResult:
    status: str
    model: str | None = None
    response: str | None = None
    error: str | None = None
    duration_s: float | None = None
    output_path: str | None = None

    @property
    def ok(self) -> bool:
        return self.status == OK


class OllamaClient:
    def __init__(self, policy: Policy | None = None, timeout: int = 300):
        self.policy = policy or Policy.load()
        self.timeout = timeout
        self._endpoint_error: str | None = None
        try:
            self.endpoint = self.policy.ollama_endpoint()
        except PaidActionBlocked as exc:
            self.endpoint = ""
            self._endpoint_error = str(exc)

    # ---- low level ---------------------------------------------------
    def _request(self, path: str, payload: dict | None = None,
                 timeout: int | None = None) -> tuple[int, Any]:
        url = f"{self.endpoint}{path}"
        data = json.dumps(payload).encode("utf-8") if payload is not None else None
        req = urllib.request.Request(
            url, data=data,
            headers={"Content-Type": "application/json"},
            method="POST" if data else "GET")
        with urllib.request.urlopen(req, timeout=timeout or self.timeout) as resp:
            body = resp.read().decode("utf-8", "replace")
        try:
            return 200, json.loads(body)
        except json.JSONDecodeError:
            return 200, body

    # ---- api ---------------------------------------------------------
    def health(self) -> dict[str, Any]:
        if self._endpoint_error:
            return {"status": BLOCKED, "endpoint": None, "error": self._endpoint_error,
                    "models": []}
        if not bool(self.policy.get("use_local_ai")):
            return {"status": BLOCKED, "endpoint": self.endpoint,
                    "error": "use_local_ai is false", "models": []}
        try:
            _, body = self._request("/api/tags", timeout=10)
        except urllib.error.URLError as exc:
            return {"status": NOT_RUNNING, "endpoint": self.endpoint,
                    "error": f"{exc.reason}", "models": [],
                    "hint": "start the local server with: ollama serve"}
        except (TimeoutError, OSError) as exc:
            return {"status": NOT_RUNNING, "endpoint": self.endpoint,
                    "error": str(exc), "models": []}
        models = [m.get("name") for m in (body or {}).get("models", [])] if isinstance(body, dict) else []
        return {
            "status": OK if models else NO_MODELS,
            "endpoint": self.endpoint,
            "models": models,
            "error": None if models else "no models pulled (ollama pull <model>)",
        }

    def generate(self, model: str, prompt: str, *,
                 system: str | None = None, save_as: str | None = None,
                 options: dict | None = None) -> OllamaResult:
        health = self.health()
        if health["status"] in (NOT_RUNNING, BLOCKED):
            return OllamaResult(status=health["status"], model=model,
                                error=health.get("error"))
        payload: dict[str, Any] = {"model": model, "prompt": prompt, "stream": False}
        if system:
            payload["system"] = system
        if options:
            payload["options"] = options
        started = datetime.now(timezone.utc)
        try:
            _, body = self._request("/api/generate", payload)
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            return OllamaResult(status=ERROR, model=model, error=str(exc))
        duration = (datetime.now(timezone.utc) - started).total_seconds()
        text = body.get("response") if isinstance(body, dict) else str(body)
        out_path = None
        if text:
            out_path = self.save_output(save_as or f"ollama_{model.replace(':', '_')}",
                                        {"model": model, "prompt": prompt,
                                         "response": text, "duration_s": duration})
        return OllamaResult(status=OK, model=model, response=text,
                            duration_s=duration,
                            output_path=paths.rel(out_path) if out_path else None)

    def pull_plan(self, model: str) -> dict[str, Any]:
        """We never auto-download models: the license gate comes first (section 8)."""
        return {
            "action": "manual",
            "command": f"ollama pull {model}",
            "reason": "model download is a human step until the exact model "
                      "license is verified and set to APPROVED in LICENSE_REGISTRY.json",
        }

    @staticmethod
    def save_output(name: str, payload: dict[str, Any]) -> Path:
        paths.AI_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        path = paths.AI_OUTPUT_DIR / f"{name}_{stamp}.json"
        payload = dict(payload)
        payload["saved_at"] = datetime.now(timezone.utc).isoformat()
        path.write_text(json.dumps(payload, indent=2, ensure_ascii=False),
                        encoding="utf-8")
        return path
