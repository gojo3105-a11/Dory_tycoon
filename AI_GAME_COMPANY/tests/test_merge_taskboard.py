"""Tests for the TASKBOARD.json three-way merge.

Run:  python3 AI_GAME_COMPANY/tests/test_merge_taskboard.py

The rule this protects: nothing anyone wrote is silently dropped. A merge
that quietly discarded a run's result would be worse than the conflict it
replaces, because the conflict at least stops and asks.
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

TOOL = Path(__file__).resolve().parents[1] / "tools" / "merge-taskboard.py"
sys.path.insert(0, str(TOOL.parent))

import importlib.util  # noqa: E402

spec = importlib.util.spec_from_file_location("merge_taskboard", TOOL)
merge_taskboard = importlib.util.module_from_spec(spec)
spec.loader.exec_module(merge_taskboard)


def board(tasks, **meta):
    data = {"_comment": "board", "_version": 1}
    data.update(meta)
    data["tasks"] = tasks
    return data


def task(task_id="T1", status="todo", notes=None, **extra):
    base = {"id": task_id, "title": "a task", "owner": "codex", "status": status,
            "goal": "", "files": [], "acceptance": [], "depends_on": [],
            "notes": list(notes or []), "changed_files": [], "last_run": ""}
    base.update(extra)
    return base


class MergeTests(unittest.TestCase):
    def merge(self, base, local, remote):
        return merge_taskboard.merge_boards(base, local, remote)

    def only(self, merged, task_id="T1"):
        return next(t for t in merged["tasks"] if t["id"] == task_id)

    def test_only_local_moved_the_status_so_local_wins(self):
        merged = self.merge(board([task()]), board([task(status="review")]),
                            board([task()]))
        self.assertEqual("review", self.only(merged)["status"])

    def test_only_upstream_moved_the_status_so_upstream_wins(self):
        merged = self.merge(board([task()]), board([task()]),
                            board([task(status="blocked")]))
        self.assertEqual("blocked", self.only(merged)["status"])

    def test_both_moved_so_the_machine_that_ran_it_wins_and_says_so(self):
        merged = self.merge(board([task()]),
                            board([task(status="review")]),
                            board([task(status="blocked")]))
        entry = self.only(merged)
        self.assertEqual("review", entry["status"])
        # The discarded claim is recorded, not dropped.
        self.assertTrue(any("upstream said 'blocked'" in n for n in entry["notes"]),
                        entry["notes"])

    def test_notes_from_both_sides_survive_in_order(self):
        merged = self.merge(
            board([task(notes=["base note"])]),
            board([task(notes=["base note", "from the run"])]),
            board([task(notes=["base note", "from claude"])]))
        self.assertEqual(["base note", "from the run", "from claude"],
                         self.only(merged)["notes"])

    def test_a_note_written_on_both_sides_is_not_duplicated(self):
        merged = self.merge(board([task()]), board([task(notes=["same"])]),
                            board([task(notes=["same"])]))
        self.assertEqual(["same"], self.only(merged)["notes"])

    def test_the_spec_text_comes_from_upstream(self):
        merged = self.merge(
            board([task()]),
            board([task(title="stale local title", files=["old.cs"])]),
            board([task(title="new spec title", files=["new.cs"],
                        title_ko="새 제목")]))
        entry = self.only(merged)
        self.assertEqual("new spec title", entry["title"])
        self.assertEqual(["new.cs"], entry["files"])
        self.assertEqual("새 제목", entry["title_ko"])

    def test_result_fields_prefer_the_side_that_has_evidence(self):
        merged = self.merge(
            board([task()]),
            board([task(changed_files=["a.cs"], last_run="C:/log.txt")]),
            board([task()]))
        entry = self.only(merged)
        self.assertEqual(["a.cs"], entry["changed_files"])
        self.assertEqual("C:/log.txt", entry["last_run"])

    def test_a_task_added_on_either_side_is_kept(self):
        merged = self.merge(
            board([task()]),
            board([task(), task("LOCAL-NEW")]),
            board([task(), task("UPSTREAM-NEW")]))
        ids = [t["id"] for t in merged["tasks"]]
        self.assertIn("LOCAL-NEW", ids)
        self.assertIn("UPSTREAM-NEW", ids)
        self.assertEqual(3, len(ids))

    def test_hand_edited_top_level_keys_survive(self):
        merged = self.merge(board([task()]), board([task()], _house="keep me"),
                            board([task()], _comment="upstream comment"))
        self.assertEqual("upstream comment", merged["_comment"])
        self.assertEqual("keep me", merged["_house"])
        self.assertEqual("tasks", list(merged)[-1])

    def test_the_real_board_merges_with_itself_unchanged(self):
        real = json.loads(
            (Path(__file__).resolve().parents[1] / "config" / "TASKBOARD.json")
            .read_text(encoding="utf-8-sig"))
        merged = self.merge(real, real, real)
        self.assertEqual(len(real["tasks"]), len(merged["tasks"]))
        for before, after in zip(real["tasks"], merged["tasks"]):
            self.assertEqual(before["id"], after["id"])
            self.assertEqual(before["status"], after["status"])
            self.assertEqual(before["notes"], after["notes"])


class CommandLineTests(unittest.TestCase):
    def run_tool(self, base, local, remote):
        with tempfile.TemporaryDirectory() as tmp:
            paths = []
            for name, data in (("base", base), ("local", local), ("remote", remote)):
                path = Path(tmp) / f"{name}.json"
                path.write_text(data if isinstance(data, str)
                                else json.dumps(data, ensure_ascii=False),
                                encoding="utf-8")
                paths.append(str(path))
            out = Path(tmp) / "out.json"
            done = subprocess.run(
                [sys.executable, str(TOOL), *paths, str(out)],
                capture_output=True, text=True, encoding="utf-8", errors="replace")
            content = out.read_text(encoding="utf-8") if out.exists() else ""
            return done.returncode, content, done.stderr

    def test_a_clean_merge_exits_zero_and_writes_valid_json(self):
        code, content, _ = self.run_tool(
            board([task()]), board([task(status="review")]), board([task()]))
        self.assertEqual(0, code)
        self.assertEqual("review", json.loads(content)["tasks"][0]["status"])

    def test_unparsable_input_refuses_rather_than_guessing(self):
        code, content, err = self.run_tool(
            board([task()]), "{ not json", board([task()]))
        self.assertEqual(2, code)
        self.assertEqual("", content)
        self.assertIn("leaving the conflict for a person", err)


if __name__ == "__main__":
    unittest.main(verbosity=2)
