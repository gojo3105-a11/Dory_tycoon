"""Loads and enforces config/company_policy.json.

Master prompt section 7. The point of this module is that a cost-prevention
rule which only exists in a JSON file is not enforcement - something has to
refuse the action. Every paid or cloud path in the orchestrator asks here
first, and a missing or unreadable policy file is treated as "deny", never as
"no restrictions".
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


class PolicyViolation(RuntimeError):
    """Raised when something asks for an action the policy forbids."""


@dataclass(frozen=True)
class Policy:
    raw: dict[str, Any] = field(default_factory=dict)
    source: Path | None = None

    # ---- construction ----------------------------------------------------

    @classmethod
    def load(cls, path: Path) -> "Policy":
        """Reads the policy file. Written by PowerShell, so it may carry a BOM."""
        text = path.read_text(encoding="utf-8-sig")
        return cls(raw=json.loads(text), source=path)

    @classmethod
    def deny_all(cls) -> "Policy":
        """The fallback when no policy file can be read: everything is off.

        Defaulting to permissive here would mean a deleted or corrupt policy
        file silently unlocks paid APIs, which is the exact failure section 7
        exists to prevent.
        """
        return cls(raw={}, source=None)

    # ---- queries ---------------------------------------------------------

    def allows(self, key: str) -> bool:
        """True only if the key is explicitly true. Unknown keys are denied."""
        return self.raw.get(key) is True

    def require(self, key: str, action: str) -> None:
        if not self.allows(key):
            where = self.source or "<no policy file loaded>"
            raise PolicyViolation(
                f"{action} is blocked: policy '{key}' is not true ({where})."
            )

    @property
    def blocked_env_keys(self) -> list[str]:
        return list(self.raw.get("blocked_env_keys", []))

    @property
    def max_retry(self) -> int:
        retry = self.raw.get("retry") or {}
        try:
            return int(retry.get("max_retry", 5))
        except (TypeError, ValueError):
            return 5

    @property
    def stop_on_repeated_error_hash(self) -> bool:
        retry = self.raw.get("retry") or {}
        return retry.get("stop_on_repeated_error_hash") is not False

    @property
    def human_gates(self) -> list[str]:
        return list(self.raw.get("human_gates", []))

    def is_human_gate(self, name: str) -> bool:
        return name in self.human_gates

    def never_auto_install(self) -> list[str]:
        return list(self.raw.get("never_auto_install", []))

    # ---- guards ----------------------------------------------------------

    def check_env_for_paid_keys(self, environ: dict[str, str]) -> list[str]:
        """Names of blocked keys present in the environment.

        Section 7: a key existing is not permission to use it. Callers use
        this to record presence and deliberately avoid the key - so this
        returns NAMES only and never touches the values.
        """
        return [name for name in self.blocked_env_keys if environ.get(name)]

    def assert_build_verification(
        self, exit_code_ok: bool, report_ok: bool, apk_exists: bool
    ) -> None:
        """Sections 18 and 32: all three must hold or the build failed.

        Section 38 forbids reporting success without an APK actually on disk,
        so this refuses to let two out of three count as a pass.
        """
        checks = self.raw.get("build_verification") or {}
        failures = []
        if checks.get("require_process_exit_code", True) and not exit_code_ok:
            failures.append("process exit code")
        if checks.get("require_unity_build_report", True) and not report_ok:
            failures.append("unity build report")
        if checks.get("require_apk_file_on_disk", True) and not apk_exists:
            failures.append("apk file on disk")

        if failures:
            raise PolicyViolation("BUILD_FAILED - missing: " + ", ".join(failures))
