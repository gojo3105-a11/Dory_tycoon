# AI_COMPANY_SETUP_REPORT

- Generated: 2026-08-27 16:54:35 UTC
- Verdict: **INFRASTRUCTURE READY (with limits recorded below)**
- Result counts: HUMAN_GATE=1, LIMITED=4, PASS=13

> Status vocabulary (master prompt sections 14, 43): **PASS** verified by a real
> command or file; **LIMITED** the component is not installed or reachable here,
> the adapter is implemented and degrades cleanly; **HUMAN_GATE** a person must
> act (login, licence, signing key, device approval); **FAIL** blocking defect.

## 0. Environment this run measured

- Host: `Linux-6.18.44-fc-v21-x86_64-with-glibc2.39`
- Company root: `/home/user/Dory_tycoon/AI_GAME_COMPANY`
- Target game project: `/home/user/Dory_tycoon`
- Active engine: **godot** (binary found: 4.3.stable.official.77dcf97d8)
- Run at: 2026-08-27T16:54:35.559824+00:00

This report describes the machine that executed it. Re-run `python3 -m company.orchestrator.main selftest` on the development PC to get that machine's real statuses - results are not transferable.

## 1. Completion checklist (master prompt section 40)

| # | Check | EXPECTED | ACTUAL | STATUS | LOG_PATH | OUTPUT_PATH |
|---|-------|----------|--------|--------|----------|-------------|
| 1 | Hardware Profiler | HARDWARE_PROFILE.json written with real OS/CPU/RAM/GPU/program data | Linux, 4 cores, 15GB RAM, GPU=False, 8 programs detected | **PASS** | - | `company/state/HARDWARE_PROFILE.json` |
| 2 | Policy Loader | company_policy.json loads and paid flags default to false | loaded_from_file=True, paid flags all false=True | **PASS** | - | `config/company_policy.json` |
| 3 | State Manager | company_state.json written atomically and reloads identically | phase=INFRASTRUCTURE, history_entries=10, atomic_write=ok | **PASS** | - | `company/state/company_state.json` |
| 4 | Task Queue (SQLite) | enqueue -> claim(RUNNING) -> PASS, and PASS refused without evidence | claimed=RUNNING, pass_without_evidence_rejected=True, final=PASS, counts={'PASS': 5} | **PASS** | - | `company/queue/tasks.sqlite3` |
| 5 | Ollama localhost call | HTTP 200 from http://localhost:11434/api/tags | NOT_RUNNING: [Errno 111] Connection refused | **LIMITED** | - | - |
| 6 | Local LLM response saved | response persisted as JSON under company/state/ai_outputs/ | write path exercised with a status record (no model available) | **LIMITED** | - | `company/state/ai_outputs/selftest_local_llm_unavailable_20260827_165426.json` |
| 7 | Codex exec test / LIMITED handling | codex exec runs, or the CODEX_LIMITED fallback engages | codex not installed; router fell back to 'claude' (chain ['codex', 'local_reasoner', 'claude']) | **LIMITED** | - | - |
| 8 | Claude Code CLI non-interactive mode | claude --help documents --print before any subprocess use | version=2.1.247 (Claude Code), --print documented=True, --output-format=True | **PASS** | - | - |
| 9 | Blender background test | blender --background --python selftest.py writes an output file | blender not installed; adapter verifies exit code AND output file when it is | **LIMITED** | - | `tools/blender/selftest.py` |
| 10 | godot batch compile/validate | headless validation exits 0 with no error lines | OK, exit=0, errors=0, warnings=4; static project check: ok=True, 3 scenes, 5 scripts, 0 broken res:// refs | **PASS** | `logs/2026-08-27/godot_validate_165434.log` | - |
| 11 | Android build test | exit 0 AND build log clean AND APK present with manifest | HUMAN_GATE: export_presets.cfg missing: an Android export preset plus debug keystore must be created once in the Godot editor (HUMAN_GATE, section 37) | **HUMAN_GATE** | - | - |
| 12 | Build log collection | every external command's stdout/stderr/exit code is written to logs/ | log file captured all fields=True, 30 log file(s) in today's folder | **PASS** | `logs/2026-08-27/selftest_log_capture_165434.log` | - |
| 13 | Report Generator | game report + AI activity report written; incomplete report refused | game_report=SELFTEST_Report.txt, activity=SELFTEST_AI_ACTIVITY.md, incomplete_rejected=True | **PASS** | - | `reports/SELFTEST_Report.txt` |
| 14 | Retry Manager | same error hash -> ROOT_CAUSE_ANALYSIS; max_retry -> NEEDS_HUMAN_REVIEW | timestamps normalised to one hash=True, repeat decision=ROOT_CAUSE_ANALYSIS, budget exhausted=NEEDS_HUMAN_REVIEW | **PASS** | - | `company/state/retry` |
| 15 | Resume test | interrupted RUNNING task is re-found after restart and a completion with a missing artifact is revoked | interrupted task recovered=True, missing-artifact completion revoked=True, problems_detected=1 | **PASS** | - | `company/state/company_state.json` |
| 16 | License Registry | UNKNOWN and unregistered assets block a release; APPROVED needs a verifier | release_allowed=False, blockers=['qwen2.5-coder', 'never_registered'], approve_without_verifier_rejected=True | **PASS** | - | `licenses/LICENSE_REGISTRY.json` |
| 17 | Paid API block test | paid keys stripped from child env; paid/purchase/remote-ollama actions raise PAID_ACTION_BLOCKED | keys stripped=['OPENAI_API_KEY', 'REPLICATE_API_TOKEN', 'ANTHROPIC_API_KEY'], paid_guard=True, purchase_guard=True, remote_ollama_blocked=True | **PASS** | - | - |
| 18 | AI routing + disagreement rule | every task kind routes to an available agent or HUMAN; reviewer conflicts are settled by the real build result | json_config->claude; build_log_triage->claude; core_system->claude; code_review->claude; release_approval->human; machine_result_wins=True | **PASS** | - | - |

## 2. Hardware profile (section 6)

```json
{
  "generated_at": "2026-08-27T16:54:24.923730+00:00",
  "profile_of": {
    "hostname": "vm",
    "note": "This file describes the machine that ran the profiler. Re-run on each machine; do not copy between machines."
  },
  "os": {
    "system": "Linux",
    "release": "6.18.44-fc-v21",
    "version": "#1 SMP PREEMPT_DYNAMIC @0",
    "machine": "x86_64",
    "platform": "Linux-6.18.44-fc-v21-x86_64-with-glibc2.39"
  },
  "cpu": {
    "processor": "x86_64",
    "core_count": 4
  },
  "ram": {
    "total_mb": 16075,
    "free_mb": 15163
  },
  "gpu": {
    "detected": false,
    "name": null,
    "vram_mb": null,
    "cuda": null,
    "source": null
  },
  "disk": {
    "root": "/home/user/Dory_tycoon/AI_GAME_COMPANY",
    "total_gb": 252.0,
    "free_gb": 29.8
  },
  "python": {
    "version": "3.11.15",
    "executable": "/usr/local/bin/python3"
  },
  "programs": {
    "python3": {
      "installed": true,
      "version": "Python 3.11.15",
      "path": "/usr/local/bin/python3",
      "status": "OK",
      "exit_code": 0
    },
    "git": {
      "installed": true,
      "version": "git version 2.43.0",
      "path": "/usr/bin/git",
      "status": "OK",
      "exit_code": 0
    },
    "node": {
      "installed": true,
      "version": "v22.22.2",
      "path": "/opt/node22/bin/node",
      "status": "OK",
      "exit_code": 0
    },
    "npm": {
      "installed": true,
      "version": "10.9.7",
      "path": "/opt/node22/bin/npm",
      "status": "OK",
      "exit_code": 0
    },
    "java": {
      "installed": true,
      "version": "Picked up JAVA_TOOL_OPTIONS: -Djavax.net.ssl.trustStore=/root/.ccr/java-truststore.p12 -Djavax.net.ssl.trustStorePassword=changeit -Djavax.net.ssl.trustStoreType=PKCS12 -Dhttps.proxyHost=127.0.0.1 -Dh",
      "path": "/usr/bin/java",
      "status": "OK",
      "exit_code": 0
    },
    "javac": {
      "installed": true,
      "version": "javac 21.0.10",
      "path": "/usr/bin/javac",
      "status": "OK",
      "exit_code": 0
    },
    "gradle": {
      "installed": true,
      "version": "------------------------------------------------------------",
      "path": "/opt/gradle/bin/gradle",
      "status": "OK",
      "exit_code": 0
    },
    "claude": {
      "installed": true,
      "version": "2.1.247 (Claude Code)",
      "path": "/opt/node22/bin/claude",
      "status": "OK",
      "exit_code": 0
    },
    "codex": {
      "installed": false,
      "version": null,
      "path": null,
      "status": "MISSING"
    },
    "ollama": {
      "installed": false,
      "version": null,
      "path": null,
      "status": "MISSING"
    },
    "blender": {
      "installed": false,
      "version": null,
      "path": null,
      "status": "MISSING"
    },
    "godot": {
      "installed": false,
      "version": null,
      "path": null,
      "status": "MISSING"
    },
    "godot4": {
      "installed": false,
      "version": null,
      "path": null,
      "status": "MISSING"
    },
    "unity": {
      "installed": false,
      "version": null,
      "path": null,
      "status": "MISSING"
    },
    "adb": {
      "installed": false,
      "version": null,
      "path": null,
      "status": "MISSING"
    },
    "aapt": {
      "installed": false,
      "version": null,
      "path": null,
      "status": "MISSING"
    },
    "ffmpeg": {
      "installed": false,
      "version": null,
      "path": null,
      "status": "MISSING"
    }
  },
  "android_sdk": {
    "installed": false,
    "path": null,
    "status": "MISSING"
  },
  "cli_capabilities": {
    "claude": {
      "print_mode": true,
      "output_format": true,
      "permission_mode": true
    }
  },
  "model_recommendation": {
    "ram_gb": 15.7,
    "vram_gb": 0.0,
    "cpu_only": true,
    "LOCAL_PLANNER": {
      "candidate": "qwen2.5-coder:1.5b",
      "license_status": "UNKNOWN",
      "usable_in_production": false,
      "note": "license must be APPROVED before production use (section 8)"
    },
    "LOCAL_REASONER": {
      "candidate": "deepseek-r1:1.5b",
      "license_status": "UNKNOWN",
      "usable_in_production": false,
      "note": "license must be APPROVED before production use (section 8)"
    },
    "image_generation": {
      "candidate": null,
      "fallback": "procedural / existing licensed assets",
      "reason": "vram 0.0GB"
    },
    "image_to_3d": {
      "candidate": null,
      "fallback": "ROUTE B pre-rigged humanoid base (section 10)",
      "reason": "vram 0.0GB"
    }
  },
  "warnings": [
    "No GPU detected: local image generation and image-to-3D fall back to procedural / existing assets (section 6).",
    "Not installed: codex, ollama, blender, godot, godot4, unity, adb, aapt, ffmpeg"
  ]
}
```

## 3. Cost policy (section 7)

```json
{
  "source": "config/company_policy.json",
  "allow_paid_api": false,
  "allow_paid_assets": false,
  "allow_cloud_ai_generation": false,
  "allow_auto_purchase": false,
  "use_local_ai": true,
  "ollama_local_only": true,
  "blocked_env_keys": [
    "ANTHROPIC_API_KEY",
    "AZURE_OPENAI_API_KEY",
    "ELEVENLABS_API_KEY",
    "FAL_KEY",
    "GEMINI_API_KEY",
    "GOOGLE_API_KEY",
    "GROQ_API_KEY",
    "HF_TOKEN",
    "HUGGINGFACE_API_TOKEN",
    "MISTRAL_API_KEY",
    "OPENAI_API_KEY",
    "REPLICATE_API_TOKEN",
    "STABILITY_API_KEY"
  ],
  "blocked_keys_present_in_env": [],
  "max_retry": 5
}
```

## 4. Company state (section 15)

```json
{
  "current_game": null,
  "current_phase": "INFRASTRUCTURE",
  "engine": "godot",
  "engine_status": "PASS",
  "codex_status": "LIMITED",
  "ollama_status": "LIMITED",
  "claude_status": "PASS",
  "blender_status": "LIMITED",
  "build_status": "HUMAN_GATE",
  "qa_status": "SELFTEST_PASS",
  "retry_count": 0,
  "completed_apk_count": 0,
  "last_completed_task": null,
  "next_task": null,
  "last_error": "build_status claimed success but APK is missing on disk",
  "updated_at": "2026-08-27T16:54:35.537874+00:00"
}
```

## 5. QA findings from this run

- engine warning (not blocking): WARNING: No Bone2D children of node Bone2D_LeftLeg. Cannot calculate bone length or angle reliably.
- engine warning (not blocking): WARNING: No Bone2D children of node Bone2D_RightLeg. Cannot calculate bone length or angle reliably.
- engine warning (not blocking): WARNING: No Bone2D children of node Bone2D_LeftArm. Cannot calculate bone length or angle reliably.
- engine warning (not blocking): WARNING: No Bone2D children of node Bone2D_RightArm. Cannot calculate bone length or angle reliably.

## 6. Next steps

1. Install Ollama on the development PC, run `ollama serve`, verify the exact model licence, set it to APPROVED in LICENSE_REGISTRY.json, then `ollama pull <model>`.
2. Install the Codex CLI and log in with the existing ChatGPT subscription (HUMAN_GATE), then re-run selftest. Until then code review falls back to local model + Claude.
3. Create the Android export preset + debug keystore once in the editor and install export templates (HUMAN_GATE), then re-run `main.py engine build`.
4. Install Blender if 3D asset processing is needed; the 2D Godot pipeline does not require it.
5. Infrastructure gate (section 41 STEP 18): create GAME_10_MASTER_PLAN.md only after the checks above are PASS on the development PC.
