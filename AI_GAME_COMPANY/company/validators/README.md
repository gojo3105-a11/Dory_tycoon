# Validators

Acceptance checks live in `company/orchestrator/artifact_validator.py`:

| Function | Checks |
|---|---|
| `file_exists` | path exists and is larger than `min_bytes` |
| `json_parses` | file exists and is valid JSON |
| `all_files_exist` | every expected output is present |
| `text_contains_no_errors` | build/validation output has no error lines |
| `apk_valid` | APK exists, is a real zip, has `AndroidManifest.xml`, optional package name via `aapt` |
| `godot_project_valid` | `project.godot` parses, main scene exists, every `res://` reference resolves |

Add engine- or game-specific validators here and call them from the task's
acceptance criteria. A task may only reach `PASS` with a validator result
attached (`task_queue.mark_pass` enforces this).
