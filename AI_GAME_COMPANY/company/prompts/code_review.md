# Code review prompt (master prompt section 17)

Used by `codex_runner.build_review_prompt()`. Inputs supplied by the caller:
changed files, requirements, engine + version, related error log, acceptance
criteria.

Checklist the reviewer must answer against:

- Compile error possibility
- NullReference / null dereference
- Event unsubscribe (leaks on scene change)
- Memory allocation in hot paths
- Per-frame update overuse (`_process` / `Update()`)
- Coroutine / async lifecycle
- Serialization
- Save file corruption
- Android compatibility
- Touch input
- Scene reference
- Asset reference
- Performance
- Race condition
- Missing reference
- Build configuration

Required output shape:

```json
{
  "critical": [{"file": "", "line": 0, "issue": "", "why": "", "fix": ""}],
  "major": [],
  "minor": [],
  "verdict": "PASS|FAIL"
}
```

A `PASS` verdict from any reviewer is an opinion, not acceptance: the task
still needs machine evidence (engine validation, tests, or a verified build).
