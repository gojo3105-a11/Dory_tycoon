"""Retry policy with error-hash deduplication (master prompt section 31).

max_retry is 5, but repeating the same error is not progress: when the same
normalised error hash comes back `same_error_hash_limit` times the decision
becomes ROOT_CAUSE_ANALYSIS instead of burning the remaining attempts.
"""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from . import paths
from .policy import Policy

RETRY = "RETRY"
ROOT_CAUSE_ANALYSIS = "ROOT_CAUSE_ANALYSIS"
NEEDS_HUMAN_REVIEW = "NEEDS_HUMAN_REVIEW"

# Volatile parts of an error message that must not affect its identity.
_NOISE = [
    (re.compile(r"\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}[.\d]*Z?"), "<TS>"),
    # Bare wall-clock times appear in build logs and must not change identity.
    (re.compile(r"\b\d{1,2}:\d{2}(?::\d{2})?(?:[.,]\d+)?\b"), "<TIME>"),
    (re.compile(r"0x[0-9a-fA-F]{4,}"), "<ADDR>"),
    (re.compile(r"(?:[A-Za-z]:)?[\\/][\w.\-\\/ ]+[\\/]"), "<PATH>/"),
    (re.compile(r"\b\d+ms\b"), "<MS>"),
    (re.compile(r"\bpid[= ]\d+\b", re.IGNORECASE), "pid=<PID>"),
    (re.compile(r"\b\d{3,}\b"), "<N>"),
]


def normalise_error(text: str) -> str:
    text = (text or "").strip()
    for pattern, repl in _NOISE:
        text = pattern.sub(repl, text)
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    # The signal is usually in the first error lines, not the full log tail;
    # keep the head bounded so long logs still hash stably.
    return "\n".join(lines[:20]).lower()


def error_hash(text: str) -> str:
    return hashlib.sha1(normalise_error(text).encode("utf-8")).hexdigest()[:16]


@dataclass
class RetryDecision:
    decision: str
    reason: str
    attempt: int
    max_retry: int
    error_hash: str
    same_hash_count: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "decision": self.decision, "reason": self.reason,
            "attempt": self.attempt, "max_retry": self.max_retry,
            "error_hash": self.error_hash, "same_hash_count": self.same_hash_count,
        }


class RetryManager:
    """Persistent per-task attempt ledger, so restarts do not reset retries."""

    def __init__(self, policy: Policy | None = None, store_dir: Path | None = None):
        self.policy = policy or Policy.load()
        self.store_dir = store_dir or paths.RETRY_DIR
        self.store_dir.mkdir(parents=True, exist_ok=True)

    def _ledger_path(self, task_id: str) -> Path:
        safe = re.sub(r"[^A-Za-z0-9_.\-]", "_", task_id)
        return self.store_dir / f"{safe}.json"

    def _load(self, task_id: str) -> dict[str, Any]:
        path = self._ledger_path(task_id)
        if path.exists():
            try:
                return json.loads(path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                pass
        return {"task_id": task_id, "attempts": []}

    def _save(self, ledger: dict[str, Any]) -> None:
        self._ledger_path(ledger["task_id"]).write_text(
            json.dumps(ledger, indent=2, ensure_ascii=False), encoding="utf-8")

    def record_failure(self, task_id: str, error_text: str,
                       *, log_path: str | None = None) -> RetryDecision:
        ledger = self._load(task_id)
        h = error_hash(error_text)
        ledger["attempts"].append({
            "at": datetime.now(timezone.utc).isoformat(),
            "error_hash": h,
            "log_path": log_path,
            "error_head": (error_text or "")[:600],
        })
        self._save(ledger)
        return self.decide(task_id)

    def decide(self, task_id: str) -> RetryDecision:
        ledger = self._load(task_id)
        attempts = ledger["attempts"]
        attempt = len(attempts)
        max_retry = int(self.policy.get("max_retry", 5))
        same_limit = int(self.policy.get("same_error_hash_limit", 2))
        current_hash = attempts[-1]["error_hash"] if attempts else ""
        same_count = sum(1 for a in attempts if a["error_hash"] == current_hash)

        if attempt == 0:
            return RetryDecision(RETRY, "no failures recorded", 0, max_retry, "", 0)
        if attempt >= max_retry:
            return RetryDecision(NEEDS_HUMAN_REVIEW,
                                 f"max_retry {max_retry} reached",
                                 attempt, max_retry, current_hash, same_count)
        if same_count >= same_limit:
            return RetryDecision(ROOT_CAUSE_ANALYSIS,
                                 f"same error hash {current_hash} seen {same_count}x; "
                                 "stop retrying and analyse root cause",
                                 attempt, max_retry, current_hash, same_count)
        return RetryDecision(RETRY, "retry budget available",
                             attempt, max_retry, current_hash, same_count)

    def attempts(self, task_id: str) -> list[dict[str, Any]]:
        return self._load(task_id)["attempts"]

    def reset(self, task_id: str) -> None:
        self._ledger_path(task_id).unlink(missing_ok=True)
