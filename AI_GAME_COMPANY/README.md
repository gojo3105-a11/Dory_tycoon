# AI_GAME_COMPANY

Local production line for AI-assisted Android game development, built from
`AI_GAME_COMPANY_EXECUTABLE_MASTER_PROMPT_V2`.

It is a real Python program, not a document: the orchestrator profiles the
machine, queues and retries tasks, drives the engine in batch mode, collects
logs, verifies artifacts on disk, and writes reports. Claude Code stays the
supervisor and high-risk implementer; the repetitive execution lives here so
work survives a closed session.

## Engine: Godot, with the Unity adapter kept

The master prompt targets Unity. This repository (`Dory_tycoon`) is a
**Godot 4.3** project, so the pipeline talks to an engine facade and
`config/engines.json` picks the adapter:

| Adapter | File | Status |
|---|---|---|
| Godot 4.x | `company/orchestrator/godot_runner.py` | active, verified against this project |
| Unity | `company/orchestrator/unity_runner.py` | implemented, reports `NOT_INSTALLED` until Unity exists |

Switch with `active_engine` in `config/engines.json`, or per command:
`main.py engine validate --engine unity`.

## Quick start

```bash
cd AI_GAME_COMPANY

python3 -m company.orchestrator.main doctor     # what is actually installed here
python3 -m company.orchestrator.main init       # create state, queue, license registry
python3 -m company.orchestrator.main selftest   # run the section 40 checklist, write the report
python3 -m company.orchestrator.main status     # state + queue + artifact verification
python3 -m unittest discover -s tests           # 33 unit tests
```

Engine work:

```bash
export GODOT_BIN=/path/to/godot            # or set config/engines.json godot.executable
python3 -m company.orchestrator.main engine caps
python3 -m company.orchestrator.main engine validate
python3 -m company.orchestrator.main engine build --out builds/Game01/game.apk
```

Tasks and licences:

```bash
python3 -m company.orchestrator.main task add --goal "Add serving queue" \
    --kind core_system --game Game01 --phase CORE_GAMEPLAY
python3 -m company.orchestrator.main task list
python3 -m company.orchestrator.main resume        # after a crash or restart
python3 -m company.orchestrator.main license gate  # can this ship?
```

`AI_GAME_COMPANY_ROOT` relocates the tree; `AI_GAME_COMPANY_PROJECT` points at
a different game project.

## Layout

```
config/           company_policy.json, model_registry.json, engines.json
company/
  orchestrator/   the program (see table below)
  agents/         department roster (agents.json)
  prompts/        review / triage / scenario prompt templates
  validators/     acceptance-check documentation
  state/          company_state.json, HARDWARE_PROFILE.json, ai_outputs/  (runtime, git-ignored)
  queue/          tasks.sqlite3                                            (runtime, git-ignored)
tools/            blender/ android/ report/
shared_assets/    reusable characters, props, audio
games/ builds/    per-game work and build output
reports/ logs/    generated reports and captured tool output
tests/            unit tests
licenses/         LICENSE_REGISTRY.json
```

| Module | Responsibility |
|---|---|
| `main.py` | CLI: doctor, init, selftest, status, engine, task, resume, license |
| `policy.py` | cost policy; strips paid API keys from child processes |
| `paths.py` | one place for every path |
| `logging_setup.py` | logging with secret redaction |
| `process_runner.py` | every external command, with EXPECTED/ACTUAL/log capture |
| `hardware_profiler.py` | HARDWARE_PROFILE.json + model size recommendation |
| `state_manager.py` | company_state.json, atomic writes, disk verification |
| `task_queue.py` | SQLite queue; PASS requires evidence |
| `retry_manager.py` | max_retry 5 with error-hash deduplication |
| `license_manager.py` | LICENSE_REGISTRY.json; UNKNOWN cannot ship |
| `artifact_validator.py` | file/JSON/APK/Godot-project acceptance checks |
| `agent_router.py` | routing by risk, fallbacks, disagreement rule |
| `ollama_client.py` | local LLM gateway, localhost-only |
| `codex_runner.py` | Codex CLI review, CODEX_LIMITED fallback |
| `claude_runner.py` | Claude CLI, enabled only if `--print` is documented |
| `blender_runner.py` | background Blender, verifies output files |
| `godot_runner.py` / `unity_runner.py` / `engine_runner.py` | engine adapters + facade |
| `report_generator.py` | setup report, game report, AI activity report |
| `selftest.py` | the section 40 checklist, executed |

## Rules the code enforces

- **No silent spending.** Paid flags default to false, paid API keys are removed
  from every child process environment, and a blocked action raises
  `PAID_ACTION_BLOCKED`. A key in the environment is not permission.
- **No unverified success.** `mark_pass()` refuses a task without machine
  evidence; a build needs exit code *and* clean log *and* the artifact on disk;
  state claiming success with a missing APK is revoked on the next verification.
- **No guessed commands.** CLI flags are read from the installed `--help`
  before use; an undocumented flag is refused rather than attempted.
- **No unlicensed release.** `UNKNOWN` or unregistered assets block the release
  gate. Code licences and model-weight licences are separate fields.
- **No infinite loops.** Five attempts maximum, and a repeated error hash
  switches to root-cause analysis instead of burning the rest.
- **No secrets in logs.** Every log record passes through redaction.

## Human gates (master prompt section 37)

Automation stops and asks only for: CLI login and terms, payment, Android
signing secrets, Google Play account, the source character image, 3D character
quality approval, and final release approval. Everything else proceeds without
asking.

## Before Game01

Section 41 STEP 18 gates game production on infrastructure verification. Run
`selftest` on the development PC and read `AI_COMPANY_SETUP_REPORT.md`; create
`GAME_10_MASTER_PLAN.md` only once the checks it lists are PASS there.
