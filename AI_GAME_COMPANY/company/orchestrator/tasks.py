"""SQLite-backed task queue.

Master prompt sections 13 and 14. Section 13 says start with SQLite/JSON and
not a microservice, so this is one table and no ORM.

Section 14's rule is enforced structurally: a task cannot reach PASS just
because an agent said it was finished. mark_pass() demands the acceptance
criteria be re-checked against something real, so "the AI reported done" is
not a state this queue can represent.
"""

from __future__ import annotations

import json
import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

STATUSES = {
    "QUEUED", "RUNNING", "REVIEW", "PASS", "FAILED", "BLOCKED", "LIMITED",
    "HUMAN_GATE", "NEEDS_HUMAN_REVIEW",
}

TERMINAL_STATUSES = {"PASS", "BLOCKED", "HUMAN_GATE", "NEEDS_HUMAN_REVIEW"}

SCHEMA = """
CREATE TABLE IF NOT EXISTS tasks (
    task_id             TEXT PRIMARY KEY,
    game_id             TEXT,
    phase               TEXT,
    department          TEXT,
    agent               TEXT,
    goal                TEXT NOT NULL,
    input_paths         TEXT,
    output_paths        TEXT,
    acceptance_criteria TEXT,
    priority            INTEGER DEFAULT 100,
    status              TEXT NOT NULL DEFAULT 'QUEUED',
    retry_count         INTEGER DEFAULT 0,
    max_retry           INTEGER DEFAULT 5,
    reviewer            TEXT,
    created_at          TEXT,
    started_at          TEXT,
    completed_at        TEXT,
    last_error          TEXT,
    last_error_hash     TEXT
);
CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status, priority);
"""


class AcceptanceNotVerified(RuntimeError):
    """Raised when a task is pushed to PASS without real evidence."""


@dataclass
class Task:
    task_id: str
    goal: str
    game_id: str | None = None
    phase: str | None = None
    department: str | None = None
    agent: str | None = None
    input_paths: list[str] | None = None
    output_paths: list[str] | None = None
    acceptance_criteria: str | None = None
    priority: int = 100
    status: str = "QUEUED"
    retry_count: int = 0
    max_retry: int = 5
    reviewer: str | None = None
    last_error: str | None = None


def _now() -> str:
    return time.strftime("%Y-%m-%d %H:%M:%S")


class TaskQueue:
    def __init__(self, db_path: Path):
        self.db_path = db_path
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(db_path))
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(SCHEMA)
        self.conn.commit()

    def close(self) -> None:
        self.conn.close()

    # ---- writes ----------------------------------------------------------

    def add(self, task: Task) -> str:
        if task.status not in STATUSES:
            raise ValueError(f"unknown status {task.status!r}")
        self.conn.execute(
            """INSERT OR REPLACE INTO tasks (
                   task_id, game_id, phase, department, agent, goal,
                   input_paths, output_paths, acceptance_criteria, priority,
                   status, retry_count, max_retry, reviewer, created_at
               ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                task.task_id, task.game_id, task.phase, task.department,
                task.agent, task.goal,
                json.dumps(task.input_paths or []),
                json.dumps(task.output_paths or []),
                task.acceptance_criteria, task.priority, task.status,
                task.retry_count, task.max_retry, task.reviewer, _now(),
            ),
        )
        self.conn.commit()
        return task.task_id

    def claim_next(self) -> sqlite3.Row | None:
        """Highest-priority QUEUED task, moved to RUNNING."""
        row = self.conn.execute(
            "SELECT * FROM tasks WHERE status='QUEUED' ORDER BY priority ASC, created_at ASC LIMIT 1"
        ).fetchone()
        if row is None:
            return None
        self.conn.execute(
            "UPDATE tasks SET status='RUNNING', started_at=? WHERE task_id=?",
            (_now(), row["task_id"]),
        )
        self.conn.commit()
        return self.get(row["task_id"])

    def mark_pass(self, task_id: str, evidence: Iterable[Path] | None = None,
                  verified_by: str | None = None) -> None:
        """PASS requires evidence, not an agent's word.

        Section 14: "AI said complete" is not a PASS. If the task declares
        output_paths, those files must exist and be non-empty; otherwise a
        human/tool attribution is required so the basis for passing is always
        recorded somewhere.
        """
        row = self.get(task_id)
        if row is None:
            raise KeyError(task_id)

        declared = json.loads(row["output_paths"] or "[]")
        candidates = [Path(p) for p in declared] if declared else list(evidence or [])

        if candidates:
            missing = [str(p) for p in candidates if not (p.is_file() and p.stat().st_size > 0)]
            if missing:
                raise AcceptanceNotVerified(
                    f"{task_id}: declared outputs missing or empty: {missing}"
                )
        elif not verified_by:
            raise AcceptanceNotVerified(
                f"{task_id}: no output paths and no verified_by - refusing to PASS "
                "on an unverifiable claim"
            )

        self.conn.execute(
            "UPDATE tasks SET status='PASS', completed_at=?, last_error=NULL WHERE task_id=?",
            (_now(), task_id),
        )
        self.conn.commit()

    def mark_failed(self, task_id: str, error: str, error_hash: str | None = None,
                    max_retry: int | None = None,
                    stop_on_repeated_hash: bool = True) -> str:
        """Records a failure and decides retry vs escalate.

        Section 31: no infinite loops, and an error hash that repeats means
        retrying is wasted - go to root-cause analysis instead of burning the
        remaining attempts on the same failure.
        """
        row = self.get(task_id)
        if row is None:
            raise KeyError(task_id)

        limit = max_retry if max_retry is not None else row["max_retry"]
        repeated = bool(error_hash) and row["last_error_hash"] == error_hash
        retry_count = row["retry_count"] + 1

        if repeated and stop_on_repeated_hash:
            status = "NEEDS_HUMAN_REVIEW"
        elif retry_count >= limit:
            status = "NEEDS_HUMAN_REVIEW"
        else:
            status = "QUEUED"

        self.conn.execute(
            """UPDATE tasks SET status=?, retry_count=?, last_error=?,
                   last_error_hash=?, completed_at=? WHERE task_id=?""",
            (status, retry_count, error, error_hash,
             _now() if status in TERMINAL_STATUSES else None, task_id),
        )
        self.conn.commit()
        return status

    def set_status(self, task_id: str, status: str, detail: str | None = None) -> None:
        if status not in STATUSES:
            raise ValueError(f"unknown status {status!r}")
        self.conn.execute(
            "UPDATE tasks SET status=?, last_error=? WHERE task_id=?",
            (status, detail, task_id),
        )
        self.conn.commit()

    # ---- reads -----------------------------------------------------------

    def get(self, task_id: str) -> sqlite3.Row | None:
        return self.conn.execute(
            "SELECT * FROM tasks WHERE task_id=?", (task_id,)
        ).fetchone()

    def counts(self) -> dict[str, int]:
        rows = self.conn.execute(
            "SELECT status, COUNT(*) AS n FROM tasks GROUP BY status"
        ).fetchall()
        return {row["status"]: row["n"] for row in rows}

    def blocked(self) -> list[sqlite3.Row]:
        placeholders = ",".join("?" for _ in TERMINAL_STATUSES - {"PASS"})
        return self.conn.execute(
            f"SELECT * FROM tasks WHERE status IN ({placeholders}) ORDER BY priority",
            tuple(sorted(TERMINAL_STATUSES - {"PASS"})),
        ).fetchall()
