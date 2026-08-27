# Build failure triage prompt (master prompt section 31)

Loop: Build -> collect log -> local reasoner first pass -> Claude fix ->
compile -> Codex review -> rebuild. `max_retry = 5`.

Give the model only what it needs:

- the failing command and its exit code
- the last 200 log lines (never the whole log)
- the changed files since the last green build
- the error hash and how many times it has already been seen

Required output shape:

```json
{
  "root_cause": "",
  "confidence": "high|medium|low",
  "category": "engine|gradle|sdk|asset|script|config|environment",
  "same_as_previous_attempt": true,
  "fix_steps": [""],
  "files_to_change": [""],
  "verification_command": ""
}
```

If `same_as_previous_attempt` is true, do not retry the same fix: the retry
manager switches to root-cause analysis instead of spending the remaining
attempts.
