"""Policy loader and cost guard (master prompt section 7).

The rule the master prompt is emphatic about: the presence of a paid API key
in the environment is NOT permission to use it. This module fails closed and
also strips blocked keys from every child process environment, so a tool we
spawn cannot silently start billing either.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from . import paths

PAID_ACTION_BLOCKED = "PAID_ACTION_BLOCKED"


class PaidActionBlocked(RuntimeError):
    """Raised when code attempts an action the policy forbids."""

    def __init__(self, action: str, reason: str):
        self.action = action
        self.reason = reason
        super().__init__(f"{PAID_ACTION_BLOCKED}: {action} ({reason})")


DEFAULTS: dict[str, Any] = {
    "allow_paid_api": False,
    "allow_paid_assets": False,
    "allow_cloud_ai_generation": False,
    "allow_auto_purchase": False,
    "use_claude_code": True,
    "use_codex_subscription": True,
    "use_local_ai": True,
    "ollama_local_only": True,
    "allow_ollama_cloud": False,
    "allow_openai_api_billing": False,
    "blocked_env_keys": [],
    "max_retry": 5,
    "same_error_hash_limit": 2,
    "ollama_endpoint": "http://localhost:11434",
    "release_requires_all_licenses_approved": True,
}


@dataclass
class Policy:
    data: dict[str, Any] = field(default_factory=lambda: dict(DEFAULTS))
    source: Path | None = None

    # ---- loading -----------------------------------------------------
    @classmethod
    def load(cls, path: Path | None = None) -> "Policy":
        path = path or paths.POLICY_FILE
        data = dict(DEFAULTS)
        if path.exists():
            loaded = json.loads(path.read_text(encoding="utf-8"))
            # Unknown keys are kept (forward compatible), known keys override.
            data.update({k: v for k, v in loaded.items() if not k.startswith("_")})
        return cls(data=data, source=path if path.exists() else None)

    def get(self, key: str, default: Any = None) -> Any:
        return self.data.get(key, DEFAULTS.get(key, default))

    def __getitem__(self, key: str) -> Any:
        return self.get(key)

    # ---- guards ------------------------------------------------------
    def guard(self, action: str, policy_key: str) -> None:
        """Raise PaidActionBlocked unless `policy_key` is true."""
        if not bool(self.get(policy_key)):
            raise PaidActionBlocked(action, f"{policy_key} is false")

    def guard_paid_api(self, action: str = "paid_api_call") -> None:
        self.guard(action, "allow_paid_api")

    def guard_cloud_generation(self, action: str = "cloud_ai_generation") -> None:
        self.guard(action, "allow_cloud_ai_generation")

    def guard_purchase(self, action: str = "auto_purchase") -> None:
        self.guard(action, "allow_auto_purchase")

    # ---- environment sanitising --------------------------------------
    @property
    def blocked_env_keys(self) -> list[str]:
        keys = list(self.get("blocked_env_keys") or [])
        if not bool(self.get("allow_openai_api_billing")):
            keys.append("OPENAI_API_KEY")
        return sorted(set(keys))

    def present_blocked_keys(self, env: dict[str, str] | None = None) -> list[str]:
        env = env if env is not None else dict(os.environ)
        return [k for k in self.blocked_env_keys if env.get(k)]

    def sanitized_env(self, env: dict[str, str] | None = None,
                      extra: dict[str, str] | None = None) -> dict[str, str]:
        """Child-process environment with paid keys removed when not allowed."""
        base = dict(env if env is not None else os.environ)
        if not bool(self.get("allow_paid_api")):
            for key in self.blocked_env_keys:
                base.pop(key, None)
        if extra:
            base.update(extra)
        return base

    # ---- ollama ------------------------------------------------------
    def ollama_endpoint(self) -> str:
        endpoint = str(self.get("ollama_endpoint") or "http://localhost:11434")
        if bool(self.get("ollama_local_only")) and not bool(self.get("allow_ollama_cloud")):
            if not any(h in endpoint for h in ("localhost", "127.0.0.1", "[::1]")):
                raise PaidActionBlocked(
                    "ollama_remote_endpoint",
                    f"ollama_local_only is true but endpoint is {endpoint}",
                )
        return endpoint.rstrip("/")

    def summary(self) -> dict[str, Any]:
        return {
            "source": paths.rel(self.source) if self.source else "DEFAULTS (file missing)",
            "allow_paid_api": self.get("allow_paid_api"),
            "allow_paid_assets": self.get("allow_paid_assets"),
            "allow_cloud_ai_generation": self.get("allow_cloud_ai_generation"),
            "allow_auto_purchase": self.get("allow_auto_purchase"),
            "use_local_ai": self.get("use_local_ai"),
            "ollama_local_only": self.get("ollama_local_only"),
            "blocked_env_keys": self.blocked_env_keys,
            "blocked_keys_present_in_env": self.present_blocked_keys(),
            "max_retry": self.get("max_retry"),
        }
