"""SQLite task queue (master prompt sections 13, 14).

Status vocabulary is fixed by the master prompt. A task only reaches PASS
through `mark_pass()`, which requires the acceptance evidence the caller
actually collected - an agent saying "done" is not accepted (section 14).
"""
from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

from . import paths

STATUSES = (
    "QUEUED", "RUNNING", "REVIEW", "PASS", "FAILED",
    "BLOCKED", "LIMITED", "HUMAN_GATE", "NEEDS_HUMAN_REVIEW",
)
TERMINAL_STATUSES = ("PASS", "BLOCKED", "HUMAN_GATE", "NEEDS_HUMAN_REVIEW")

SCHEMA = """
CREATE TABLE IF NOT EXISTS tasks (
    task_id             TEXT PRIMARY KEY,
    game_id             TEXT,
    phase               TEXT,
    department          TEXT,
    agent               TEXT,
    goal                TEXT NOT NULL,
    input_paths         TEXT NOT NULL DEFAULT '[]',
    output_paths        TEXT NOT NULL DEFAULT '[]',
    acceptance_criteria TEXT NOT NULL DEFAULT '[]',
    priority            INTEGER NOT NULL DEFAULT 100,
    status              TEXT NOT NULL DEFAULT 'QUEUED',
    retry_count         INTEGER NOT NULL DEFAULT 0,
    max_retry           INTEGER NOT NULL DEFAULT 5,
    reviewer            TEXT,
    created_at          TEXT NOT NULL,
    started_at          TEXT,
    completed_at        TEXT,
    last_error          TEXT,
    evidence            TEXT
);
CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status, priority, created_at);
CREATE TABLE IF NOT EXISTS task_history (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id   TEXT NOT NULL,
    at        TEXT NOT NULL,
    from_status TEXT,
    to_status TEXT,
    note      TEXT
);
"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class Task:
    task_id: str
    goal: str
    game_id: str | None = None
    phase: str | None = None
    department: str | None = None
    agent: str | None = None
    input_paths: list[str] = None
    output_paths: list[str] = None
    acceptance_criteria: list[str] = None
    priority: int = 100
    status: str = "QUEUED"
    retry_count: int = 0
    max_retry: int = 5
    reviewer: str | None = None
    created_at: str | None = None
    started_at: str | None = None
    completed_at: str | None = None
    last_error: str | None = None
    evidence: dict | None = None

    def __post_init__(self):
        self.input_paths = self.input_paths or []
        self.output_paths = self.output_paths or []
        self.acceptance_criteria = self.acceptance_criteria or []

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class TaskQueue:
    def __init__(self, db_path: Path | str = paths.TASK_DB_FILE):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._conn() as conn:
            conn.executescript(SCHEMA)

    @contextmanager
    def _conn(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(str(self.db_path), timeout=30)
        conn.row_factory = sqlite3.Row
        try:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA foreign_keys=ON")
            yield conn
            conn.commit()
        finally:
            conn.close()

    # ---- write -------------------------------------------------------
    def enqueue(self, task: Task) -> Task:
        if task.status not in STATUSES:
            raise ValueError(f"invalid status: {task.status}")
        task.created_at = task.created_at or _now()
        with self._conn() as conn:
            conn.execute(
                """INSERT OR REPLACE INTO tasks
                   (task_id, game_id, phase, department, agent, goal, input_paths,
                    output_paths, acceptance_criteria, priority, status, retry_count,
                    max_retry, reviewer, created_at, started_at, completed_at,
                    last_error, evidence)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (task.task_id, task.game_id, task.phase, task.department, task.agent,
                 task.goal, json.dumps(task.input_paths), json.dumps(task.output_paths),
                 json.dumps(task.acceptance_criteria), task.priority, task.status,
                 task.retry_count, task.max_retry, task.reviewer, task.created_at,
                 task.started_at, task.completed_at, task.last_error,
                 json.dumps(task.evidence) if task.evidence else None),
            )
            conn.execute(
                "INSERT INTO task_history (task_id, at, from_status, to_status, note)"
                " VALUES (?,?,?,?,?)",
                (task.task_id, _now(), None, task.status, "enqueued"))
        return task

    def claim_next(self, *, agent: str | None = None) -> Task | None:
        """Take the highest-priority QUEUED task and mark it RUNNING."""
        with self._conn() as conn:
            sql = ("SELECT * FROM tasks WHERE status='QUEUED'"
                   + (" AND agent=?" if agent else "")
                   + " ORDER BY priority ASC, created_at ASC LIMIT 1")
            row = conn.execute(sql, (agent,) if agent else ()).fetchone()
            if row is None:
                return None
            now = _now()
            conn.execute("UPDATE tasks SET status='RUNNING', started_at=? WHERE task_id=?",
                         (now, row["task_id"]))
            conn.execute(
                "INSERT INTO task_history (task_id, at, from_status, to_status, note)"
                " VALUES (?,?,?,?,?)", (row["task_id"], now, "QUEUED", "RUNNING", "claimed"))
        return self.get(row["task_id"])

    def claim(self, task_id: str) -> Task:
        """Claim one specific task. Use when the caller already knows which
        task it is running; `claim_next` picks by priority instead."""
        with self._conn() as conn:
            row = conn.execute("SELECT status FROM tasks WHERE task_id=?",
                               (task_id,)).fetchone()
            if row is None:
                raise KeyError(task_id)
            if row["status"] != "QUEUED":
                raise ValueError(f"{task_id} is {row['status']}, not QUEUED")
            now = _now()
            conn.execute("UPDATE tasks SET status='RUNNING', started_at=? WHERE task_id=?",
                         (now, task_id))
            conn.execute(
                "INSERT INTO task_history (task_id, at, from_status, to_status, note)"
                " VALUES (?,?,?,?,?)", (task_id, now, "QUEUED", "RUNNING", "claimed by id"))
        return self.get(task_id)

    def set_status(self, task_id: str, status: str, *, note: str | None = None,
                   last_error: str | None = None, evidence: dict | None = None) -> Task:
        if status not in STATUSES:
            raise ValueError(f"invalid status: {status}")
        with self._conn() as conn:
            row = conn.execute("SELECT status FROM tasks WHERE task_id=?", (task_id,)).fetchone()
            if row is None:
                raise KeyError(task_id)
            now = _now()
            completed = now if status in TERMINAL_STATUSES else None
            conn.execute(
                """UPDATE tasks SET status=?, last_error=COALESCE(?, last_error),
                       evidence=COALESCE(?, evidence), completed_at=?
                   WHERE task_id=?""",
                (status, last_error, json.dumps(evidence) if evidence else None,
                 completed, task_id))
            conn.execute(
                "INSERT INTO task_history (task_id, at, from_status, to_status, note)"
                " VALUES (?,?,?,?,?)", (task_id, now, row["status"], status, note))
        return self.get(task_id)

    def mark_pass(self, task_id: str, evidence: dict) -> Task:
        """PASS requires machine-checked evidence (section 14)."""
        if not evidence:
            raise ValueError("PASS requires evidence; an agent's word is not enough")
        if not evidence.get("acceptance_checked"):
            raise ValueError("evidence must include acceptance_checked=True")
        return self.set_status(task_id, "PASS", note="acceptance verified",
                               evidence=evidence)

    def bump_retry(self, task_id: str, error: str) -> Task:
        with self._conn() as conn:
            conn.execute(
                "UPDATE tasks SET retry_count = retry_count + 1, last_error=? WHERE task_id=?",
                (error[:4000], task_id))
        return self.get(task_id)

    # ---- read --------------------------------------------------------
    def get(self, task_id: str) -> Task | None:
        with self._conn() as conn:
            row = conn.execute("SELECT * FROM tasks WHERE task_id=?", (task_id,)).fetchone()
        return self._row_to_task(row) if row else None

    def list(self, *, status: str | None = None, game_id: str | None = None,
             limit: int = 200) -> list[Task]:
        clauses, args = [], []
        if status:
            clauses.append("status=?")
            args.append(status)
        if game_id:
            clauses.append("game_id=?")
            args.append(game_id)
        where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
        with self._conn() as conn:
            rows = conn.execute(
                f"SELECT * FROM tasks{where} ORDER BY priority ASC, created_at ASC LIMIT ?",
                (*args, limit)).fetchall()
        return [self._row_to_task(r) for r in rows]

    def counts(self) -> dict[str, int]:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT status, COUNT(*) c FROM tasks GROUP BY status").fetchall()
        return {r["status"]: r["c"] for r in rows}

    def history(self, task_id: str) -> list[dict[str, Any]]:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT at, from_status, to_status, note FROM task_history"
                " WHERE task_id=? ORDER BY id ASC", (task_id,)).fetchall()
        return [dict(r) for r in rows]

    def resume_candidates(self) -> list[Task]:
        """Tasks left mid-flight by a crash, plus anything still queued."""
        out: list[Task] = []
        for status in ("RUNNING", "REVIEW", "FAILED", "LIMITED", "QUEUED"):
            out.extend(self.list(status=status))
        return out

    @staticmethod
    def _row_to_task(row: sqlite3.Row) -> Task:
        return Task(
            task_id=row["task_id"], goal=row["goal"], game_id=row["game_id"],
            phase=row["phase"], department=row["department"], agent=row["agent"],
            input_paths=json.loads(row["input_paths"] or "[]"),
            output_paths=json.loads(row["output_paths"] or "[]"),
            acceptance_criteria=json.loads(row["acceptance_criteria"] or "[]"),
            priority=row["priority"], status=row["status"],
            retry_count=row["retry_count"], max_retry=row["max_retry"],
            reviewer=row["reviewer"], created_at=row["created_at"],
            started_at=row["started_at"], completed_at=row["completed_at"],
            last_error=row["last_error"],
            evidence=json.loads(row["evidence"]) if row["evidence"] else None,
        )
