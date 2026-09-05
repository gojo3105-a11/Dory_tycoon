#!/usr/bin/env python3
"""Three-way merge for TASKBOARD.json, so a sync is never blocked by it.

WHY THIS EXISTS. The board is edited on both sides by design: Claude writes
specs and review notes upstream, and every `team run` on the build PC writes
status, changed_files and notes locally. Git sees one JSON file and calls it
a conflict, which stopped the scheduled sync three times in a row on
2026-09-05 - and a stopped sync is how a whole day's work went unnoticed
once already.

The merge is safe because of what the board actually is:

  NOTES ARE APPEND-ONLY. Both sides' notes are kept, in base order first,
  then each side's additions. Nothing a person or a run wrote is dropped.

  A STATUS CHANGED BY A RUN OUTRANKS ONE CHANGED BY HAND. When only one side
  moved a status, that side wins. When BOTH moved it, LOCAL wins - local is
  the machine that actually ran the task - and the discarded value is written
  into the notes rather than vanishing. This file never silently loses a
  claim about what happened.

  RESULT FIELDS PREFER EVIDENCE. changed_files and last_run take whichever
  side is non-empty; if both are, local wins, for the same reason.

Tasks present on only one side are kept. Unknown top-level keys are kept.
Exits 0 on success, 2 when it cannot parse an input - in which case the
caller must leave the conflict to a person.

Usage:  merge-taskboard.py <base> <local> <remote> <output>
"""

from __future__ import annotations

import json
import sys
from collections import OrderedDict
from typing import Any

# Ordered worst-to-best only for reporting; it is NOT used to auto-promote a
# status, because "further along" is a judgement a person or a run makes.
STATUS_ORDER = ("todo", "in_progress", "blocked", "review", "done")


def load(path: str) -> dict[str, Any]:
    with open(path, encoding="utf-8-sig") as handle:
        return json.load(handle, object_pairs_hook=OrderedDict)


def merge_notes(base: list[str], local: list[str], remote: list[str]) -> list[str]:
    """Base order first, then each side's additions, without duplicates."""
    merged: list[str] = []
    seen: set[str] = set()
    for note in list(base) + list(local) + list(remote):
        if note not in seen:
            seen.add(note)
            merged.append(note)
    return merged


def merge_task(base: dict[str, Any] | None, local: dict[str, Any],
               remote: dict[str, Any]) -> dict[str, Any]:
    base = base or {}
    merged = OrderedDict(remote)
    merged.update({k: v for k, v in local.items() if k not in merged})

    # Fields a spec owns: upstream (remote) is where specs are written, so it
    # wins on the text of the task itself.
    for field in ("title", "title_ko", "goal", "files", "acceptance", "depends_on"):
        if field in remote:
            merged[field] = remote[field]
        elif field in local:
            merged[field] = local[field]

    notes = merge_notes(base.get("notes", []), local.get("notes", []),
                        remote.get("notes", []))

    base_status = base.get("status")
    local_status = local.get("status", base_status)
    remote_status = remote.get("status", base_status)

    if local_status == remote_status:
        merged["status"] = local_status
    elif remote_status == base_status:
        merged["status"] = local_status          # only local moved
    elif local_status == base_status:
        merged["status"] = remote_status         # only remote moved
    else:
        # Both moved. The machine that ran the task is the better witness,
        # and the other claim is recorded rather than dropped.
        merged["status"] = local_status
        notes.append(
            f"MERGE {base_status or '?'} -> local '{local_status}' kept, "
            f"upstream said '{remote_status}'. Both sides changed this status; "
            "the side that ran the task won. Check which is right.")

    merged["notes"] = notes
    for field in ("changed_files", "last_run"):
        merged[field] = local.get(field) or remote.get(field) or base.get(field) or (
            [] if field == "changed_files" else "")
    return merged


def merge_boards(base: dict[str, Any], local: dict[str, Any],
                 remote: dict[str, Any]) -> dict[str, Any]:
    merged = OrderedDict((k, v) for k, v in remote.items() if k != "tasks")
    for key, value in local.items():
        if key != "tasks" and key not in merged:
            merged[key] = value

    def by_id(board: dict[str, Any]) -> dict[str, dict[str, Any]]:
        return {t.get("id"): t for t in board.get("tasks", []) if t.get("id")}

    base_tasks, local_tasks, remote_tasks = by_id(base), by_id(local), by_id(remote)

    order: list[str] = []
    for board in (remote, local):
        for task in board.get("tasks", []):
            task_id = task.get("id")
            if task_id and task_id not in order:
                order.append(task_id)

    tasks = []
    for task_id in order:
        in_local, in_remote = local_tasks.get(task_id), remote_tasks.get(task_id)
        if in_local and in_remote:
            tasks.append(merge_task(base_tasks.get(task_id), in_local, in_remote))
        else:
            # Added on one side only - keep it as written.
            tasks.append(in_local or in_remote)
    merged["tasks"] = tasks
    return merged


def main(argv: list[str]) -> int:
    if len(argv) != 5:
        print(__doc__.strip().splitlines()[-1], file=sys.stderr)
        return 2
    try:
        base, local, remote = (load(argv[i]) for i in (1, 2, 3))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"merge-taskboard: cannot read an input ({exc}) - leaving the "
              "conflict for a person.", file=sys.stderr)
        return 2

    merged = merge_boards(base, local, remote)
    with open(argv[4], "w", encoding="utf-8") as handle:
        json.dump(merged, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    print(f"merge-taskboard: merged {len(merged.get('tasks', []))} tasks into {argv[4]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
