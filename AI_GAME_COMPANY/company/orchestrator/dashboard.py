"""Renders Reports/dashboard.html - which AI can work, and on what.

WHY THIS EXISTS. Eight AI-ish tools are installed on the build PC, and asking
"what is connected?" gets you a list of eight. That list is misleading: the
only local LLM installed does not fit in this machine's RAM, the image model
has no weights on disk yet, Blender has no adapter, and every paid API is
switched off by policy. The useful question is not what is installed but what
can actually do work right now, and what is holding back the rest.

So every row on this page carries its EVIDENCE - the file the status was read
from. Where there is no file, the row says "근거 없음" rather than guessing.
That is section 38 made visible: a claim with nothing behind it is not a
status, and a dashboard that quietly upgrades "not checked" to "OK" is worse
than no dashboard.

Nothing here probes the network or the machine. It reads committed files, so
it produces the same answer from the build PC and from a container that has
never seen Unity.
"""

from __future__ import annotations

import html
import json
import re
import subprocess
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# Status vocabulary. Deliberately four, not three: "not checked" is its own
# state and must never collapse into either OK or broken.
READY = "ready"        # can do work now
GATED = "gated"        # blocked on a person or a one-off setup step
BLOCKED = "blocked"    # cannot work on this machine / forbidden by policy
UNKNOWN = "unknown"    # no evidence in the repository

STATE_LABEL = {
    READY: "작업 가능",
    GATED: "대기 중",
    BLOCKED: "사용 불가",
    UNKNOWN: "확인 불가",
}


@dataclass
class Agent:
    name: str
    role: str
    state: str
    detail: str
    version: str = ""
    evidence: list[str] = field(default_factory=list)


@dataclass
class Snapshot:
    """Everything the page shows, read once so rendering stays pure."""
    generated_at: str
    profile: dict[str, Any]
    policy: dict[str, Any]
    licences: dict[str, str]
    tasks: list[dict[str, Any]]
    agents: list[Agent]
    builds: list[dict[str, str]]
    build_report_at: str
    errors: dict[str, int]
    error_report_at: str
    games: list[dict[str, Any]]
    commits: list[dict[str, str]]
    missing: list[str]


# ---- reading -------------------------------------------------------------


def _read_json(path: Path) -> dict[str, Any]:
    """Missing or unparsable reads as empty. The caller reports the absence."""
    if not path.is_file():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except (json.JSONDecodeError, OSError):
        return {}


def _licence_status(registry: dict[str, Any]) -> dict[str, str]:
    return {
        entry.get("id", ""): entry.get("status", "UNKNOWN")
        for entry in registry.get("entries", [])
        if isinstance(entry, dict)
    }


def _report_timestamp(text: str) -> str:
    match = re.search(r"^Generated:\s*(.+)$", text, re.MULTILINE)
    return match.group(1).strip() if match else ""


def read_builds(path: Path) -> tuple[list[dict[str, str]], str]:
    """Real APK/AAB files, from the report that scans the PC's Builds folder.

    This is the only evidence of a build that reaches the repository - there
    is no GitHub Actions API access here - so a game with no line in this file
    has no verified APK, whatever any other document claims.
    """
    if not path.is_file():
        return [], ""

    text = path.read_text(encoding="utf-8-sig", errors="replace")
    builds = []
    pattern = re.compile(
        r"^-\s+\[(?P<where>[^\]]+)\]\s+(?P<file>\S+)\s+"
        r"\((?P<size>[\d.]+\s*[KMG]B),\s*sha256:(?P<sha>[0-9A-Fa-f]+),\s*"
        r"built (?P<built>[^)]+)\)",
        re.MULTILINE,
    )
    for match in pattern.finditer(text):
        name = match.group("file").replace("\\", "/")
        game = ""
        parts = name.split("/")
        if "Builds" in parts:
            index = parts.index("Builds")
            if index + 1 < len(parts):
                game = parts[index + 1]
        builds.append({
            "game": game,
            "file": parts[-1],
            "path": name,
            "size": match.group("size"),
            "sha": match.group("sha"),
            "built": match.group("built").strip(),
            "where": match.group("where"),
        })
    return builds, _report_timestamp(text)


def read_errors(path: Path) -> tuple[dict[str, int], str]:
    """Compile errors, obsolete-API warnings and runtime exceptions."""
    if not path.is_file():
        return {}, ""

    text = path.read_text(encoding="utf-8-sig", errors="replace")
    counts: dict[str, int] = {}
    for label, key in (
        ("Compile errors", "compile"),
        ("Obsolete API warnings", "obsolete"),
        ("Runtime exceptions", "runtime"),
    ):
        # The count is the LAST bracket on the heading line, not the first:
        # "## Obsolete API warnings (CS0618) (0)" carries the rule id in its
        # own brackets first. A pattern that stopped at the first "(" silently
        # matched nothing here, and the renderer's default turned that into a
        # confident "0" - the exact false-clean this page exists to prevent.
        match = re.search(rf"^##\s+{re.escape(label)}.*\((\d+)\)\s*$", text, re.MULTILINE)
        if match:
            counts[key] = int(match.group(1))
    return counts, _report_timestamp(text)


def read_commits(repo_root: Path, limit: int = 8) -> list[dict[str, str]]:
    """Recent history. Best effort - a dashboard is not worth failing over."""
    try:
        completed = subprocess.run(
            ["git", "log", f"-{limit}", "--date=short",
             "--pretty=format:%h\x1f%ad\x1f%s"],
            cwd=str(repo_root), capture_output=True, text=True, timeout=20, check=True,
        )
    except (OSError, subprocess.SubprocessError):
        return []

    commits = []
    for line in completed.stdout.splitlines():
        parts = line.split("\x1f")
        if len(parts) == 3:
            commits.append({"sha": parts[0], "date": parts[1], "subject": parts[2]})
    return commits


# ---- the roster ----------------------------------------------------------


def build_agents(profile: dict[str, Any], policy: dict[str, Any],
                 licences: dict[str, str], company_root: Path) -> list[Agent]:
    """Work out what each AI can actually do, and say what the evidence was.

    Every branch here answers one question: is there a file in this repository
    that says this thing works? "Installed" is never enough on its own - a
    model that is installed, licensed and too big for RAM is still unusable,
    and the row has to say which of the three failed.
    """
    tools = profile.get("tools", {})
    profile_evidence = "config/HARDWARE_PROFILE.json"
    policy_evidence = "config/company_policy.json"
    licence_evidence = "config/LICENSE_REGISTRY.json"
    has_profile = bool(profile)

    ram_total = float(profile.get("hardware", {}).get("ramTotalGb") or 0)
    agents: list[Agent] = []

    def tool(name: str) -> dict[str, Any]:
        return tools.get(name, {}) if isinstance(tools.get(name), dict) else {}

    # --- Claude Code ---
    claude = tool("claude")
    if not has_profile:
        agents.append(Agent("Claude Code", "설계 · 구현 · 리뷰", UNKNOWN,
                            "환경 리포트가 없습니다. detect-environment.ps1을 먼저 실행하세요.",
                            evidence=[]))
    elif claude.get("installed") and policy.get("use_claude_code") is True:
        agents.append(Agent(
            "Claude Code", "설계 · 구현 · 리뷰", READY,
            "코드를 직접 작성합니다. 커밋은 사람 승인 후에만 합니다.",
            str(claude.get("version", "")), [profile_evidence, policy_evidence]))
    else:
        agents.append(Agent(
            "Claude Code", "설계 · 구현 · 리뷰", BLOCKED,
            "설치되지 않았거나 정책 use_claude_code 가 켜져 있지 않습니다.",
            str(claude.get("version", "")), [profile_evidence, policy_evidence]))

    # --- Codex ---
    codex = tool("codex")
    if not codex.get("installed"):
        agents.append(Agent("Codex CLI", "공동 개발 · 독립 리뷰", UNKNOWN,
                            "환경 리포트에 codex 항목이 없습니다.", "", [profile_evidence]))
    elif policy.get("use_codex_subscription") is not True:
        agents.append(Agent(
            "Codex CLI", "공동 개발 · 독립 리뷰", BLOCKED,
            "정책 use_codex_subscription 이 false 입니다.",
            str(codex.get("version", "")), [policy_evidence]))
    else:
        writes = policy.get("allow_codex_write") is True
        # Login is deliberately not inferred: ~/.codex/auth.json is on the
        # policy's secrets_never_touched list, so nothing here may read it,
        # and initial_codex_login is a HUMAN_GATE.
        agents.append(Agent(
            "Codex CLI",
            "공동 개발 · 독립 리뷰" if writes else "독립 리뷰 전용",
            GATED,
            ("작업판에서 작업을 넘겨받아 코드를 직접 씁니다 (workspace-write). "
             if writes else "쓰기 권한 없음 - 정책 allow_codex_write 가 false 입니다. ")
            + "로그인 상태는 여기서 확인하지 않습니다. PC에서 "
              "'orchestrator codex --doctor' 로 확인하세요.",
            str(codex.get("version", "")), [profile_evidence, policy_evidence]))

    # --- Ollama and whatever model is actually installed ---
    api = profile.get("ollamaApi", {}) if isinstance(profile.get("ollamaApi"), dict) else {}
    models = api.get("models") or []
    if not tool("ollama").get("installed"):
        agents.append(Agent("Ollama (로컬 LLM)", "로컬 추론", UNKNOWN,
                            "환경 리포트에 ollama 항목이 없습니다.", "", [profile_evidence]))
    elif not models:
        agents.append(Agent(
            "Ollama (로컬 LLM)", "로컬 추론", GATED,
            "설치된 모델이 없습니다. 라이선스 확인 후 3B급 모델을 받아야 합니다.",
            str(tool("ollama").get("version", "")), [profile_evidence]))
    else:
        for model in models:
            model_id = str(model.get("name", "?"))
            size = float(model.get("sizeGb") or 0)
            status = licences.get(model_id, "UNKNOWN")
            reasons = []
            # Both checks run: a model can pass the licence gate and still be
            # unloadable, and naming only the first failure hides the second.
            if status != "APPROVED":
                reasons.append(f"라이선스 {status}")
            if ram_total and size >= ram_total * 0.8:
                reasons.append(f"{size:.1f} GB 모델 / 전체 RAM {ram_total:.1f} GB - 적재 불가")
            agents.append(Agent(
                f"Ollama · {model_id}", "로컬 추론",
                BLOCKED if reasons else READY,
                " · ".join(reasons) if reasons
                else f"{model.get('parameterSize', '')} {model.get('quantization', '')}".strip(),
                str(tool("ollama").get("version", "")),
                [profile_evidence, licence_evidence]))

    # --- local image generation ---
    generated = company_root / "generated"
    produced = list(generated.rglob("*.png")) if generated.is_dir() else []
    sd_status = licences.get("stable-diffusion-v1-5", "UNKNOWN")
    if policy.get("allow_local_image_generation") is not True:
        agents.append(Agent(
            "Stable Diffusion 1.5 + IP-Adapter", "캐릭터 스프라이트 생성", BLOCKED,
            "정책 allow_local_image_generation 이 false 입니다.",
            "", [policy_evidence]))
    elif produced:
        agents.append(Agent(
            "Stable Diffusion 1.5 + IP-Adapter", "캐릭터 스프라이트 생성", READY,
            f"생성된 이미지 {len(produced)}장이 저장소에 있습니다.",
            "", [licence_evidence, "AI_GAME_COMPANY/generated/"]))
    else:
        agents.append(Agent(
            "Stable Diffusion 1.5 + IP-Adapter", "캐릭터 스프라이트 생성", GATED,
            f"라이선스 {sd_status}. 가중치가 아직 없습니다 - 이 컨테이너에서는 "
            "huggingface.co 가 프록시에서 403 이라 받을 수 없고, PC에서 "
            "setup-image-generation.ps1 을 실행해야 합니다.",
            "", [licence_evidence, policy_evidence]))

    # --- Qwen-Image: approved, and still unusable here ---
    if licences.get("qwen-image", "").startswith("APPROVED_BUT_UNUSABLE"):
        agents.append(Agent(
            "Qwen-Image", "고품질 이미지 생성", BLOCKED,
            f"라이선스는 통과했지만 약 18.5 GB 가 필요합니다. 이 PC 전체 RAM 은 "
            f"{ram_total:.1f} GB 입니다.",
            "", [licence_evidence]))

    # --- Blender: installed, but nothing drives it yet ---
    blender = tool("blender")
    if blender.get("installed"):
        has_adapter = (company_root / "company" / "orchestrator" / "blender_runner.py").is_file()
        agents.append(Agent(
            "Blender", "3D 캐릭터 · 렌더",
            READY if has_adapter else UNKNOWN,
            "어댑터 연결됨." if has_adapter
            else "설치는 확인됐지만 이걸 호출하는 코드가 아직 없습니다 (blender_runner.py 미구현).",
            str(blender.get("version", "")), [profile_evidence]))

    # --- paid APIs: off by policy, and that is the desired state ---
    present = [k for k, v in (profile.get("paidApiKeysPresent") or {}).items() if v]
    agents.append(Agent(
        "유료 API (OpenAI · Anthropic · Google 등)", "사용 안 함", BLOCKED,
        ("정책상 차단되어 있습니다. 환경에 있는 키: " + ", ".join(present) +
         " - 존재해도 사용하지 않으며, 자식 프로세스 환경에서 제거됩니다.")
        if present else
        "정책상 차단되어 있고, 환경에 키도 없습니다. 비용이 발생하는 경로가 없습니다.",
        "", [profile_evidence, policy_evidence]))

    return agents


def read_games(repo_root: Path, builds: list[dict[str, str]],
               total: int = 10) -> list[dict[str, Any]]:
    """The 10-game plan against what actually exists.

    A game counts as done only with BOTH a written report and a real APK in
    the build report. Either one alone is a claim, not a finished game.
    """
    spec_dir = repo_root / "GameSpecs"
    specs = sorted(p.stem for p in spec_dir.glob("*.json")) if spec_dir.is_dir() else []
    built = {b["game"] for b in builds if b.get("game")}

    games = []
    for index in range(1, total + 1):
        game_id = f"game{index:02d}"
        has_spec = game_id in specs
        has_report = (repo_root / "Reports" / f"Game{index:02d}_Report.txt").is_file()
        has_apk = game_id in built
        if has_report and has_apk:
            state = "done"
        elif has_spec:
            state = "active"
        else:
            state = "todo"
        games.append({"id": game_id, "state": state, "spec": has_spec,
                      "report": has_report, "apk": has_apk})
    return games


def collect(repo_root: Path) -> Snapshot:
    company_root = repo_root / "AI_GAME_COMPANY"
    config = company_root / "config"

    profile = _read_json(config / "HARDWARE_PROFILE.json")
    policy = _read_json(config / "company_policy.json")
    registry = _read_json(config / "LICENSE_REGISTRY.json")
    board = _read_json(config / "TASKBOARD.json")

    builds, build_at = read_builds(repo_root / "Reports" / "build-status" / "latest.txt")
    errors, error_at = read_errors(repo_root / "Reports" / "errors" / "latest.txt")

    missing = [name for name, data in (
        ("config/HARDWARE_PROFILE.json", profile),
        ("config/company_policy.json", policy),
        ("config/LICENSE_REGISTRY.json", registry),
        ("config/TASKBOARD.json", board),
    ) if not data]
    if not builds:
        missing.append("Reports/build-status/latest.txt")

    licences = _licence_status(registry)
    return Snapshot(
        generated_at=datetime.now(timezone.utc).astimezone().strftime("%Y-%m-%d %H:%M"),
        profile=profile,
        policy=policy,
        licences=licences,
        tasks=board.get("tasks", []),
        agents=build_agents(profile, policy, licences, company_root),
        builds=builds,
        build_report_at=build_at,
        errors=errors,
        error_report_at=error_at,
        games=read_games(repo_root, builds),
        commits=read_commits(repo_root),
        missing=missing,
    )


# ---- rendering -----------------------------------------------------------

def e(value: Any) -> str:
    return html.escape(str(value), quote=True)


CSS = """
:root{
  --ground:#EBEEF2; --surface:#FFFFFF; --surface-2:#F5F7FA; --sunk:#E3E8EE;
  --ink:#17222E; --ink-2:#39485A; --muted:#61707F; --line:#D6DEE6;
  --accent:#12657F; --accent-soft:#DCEDF3;
  --ok:#0C6F58; --ok-soft:#DCF0E9;
  --gate:#8E5205; --gate-soft:#FAEBD6;
  --blocked:#A32B22; --blocked-soft:#F8E2E0;
  --unknown:#5A6472; --unknown-soft:#E6E9ED;
  /* Severity slot, overridden per element by the .s-* / .g-* classes below.
     Defined here so an element that somehow renders without one of those
     classes gets the neutral colour rather than no colour at all. */
  --st:var(--unknown); --st-soft:var(--unknown-soft);
}
@media (prefers-color-scheme: dark){
  :root:not([data-theme="light"]){
    --ground:#0E1319; --surface:#161D25; --surface-2:#1C242E; --sunk:#111820;
    --ink:#E7EEF4; --ink-2:#BCC8D4; --muted:#8E9CAB; --line:#2A3542;
    --accent:#5FBBDA; --accent-soft:#123340;
    --ok:#43CCA1; --ok-soft:#0F3830;
    --gate:#E5A94A; --gate-soft:#3A2B12;
    --blocked:#F5837B; --blocked-soft:#3D1E1C;
    --unknown:#9AA6B4; --unknown-soft:#232B34;
  }
}
:root[data-theme="dark"]{
  --ground:#0E1319; --surface:#161D25; --surface-2:#1C242E; --sunk:#111820;
  --ink:#E7EEF4; --ink-2:#BCC8D4; --muted:#8E9CAB; --line:#2A3542;
  --accent:#5FBBDA; --accent-soft:#123340;
  --ok:#43CCA1; --ok-soft:#0F3830;
  --gate:#E5A94A; --gate-soft:#3A2B12;
  --blocked:#F5837B; --blocked-soft:#3D1E1C;
  --unknown:#9AA6B4; --unknown-soft:#232B34;
}

*{box-sizing:border-box;}
body{
  margin:0; background:var(--ground); color:var(--ink);
  font-family:'Noto Sans KR','Archivo',-apple-system,'Malgun Gothic',sans-serif;
  font-size:15px; line-height:1.6; -webkit-font-smoothing:antialiased;
}
.wrap{max-width:1080px; margin:0 auto; padding:32px 24px 72px;}

h1,h2,h3{font-family:'Archivo','Noto Sans KR',sans-serif; text-wrap:balance; margin:0;}
h1{font-size:30px; font-weight:700; letter-spacing:-0.015em;}
h2{font-size:15px; font-weight:700; letter-spacing:0.09em; text-transform:uppercase;
   color:var(--muted);}
.mono{font-family:'JetBrains Mono',ui-monospace,'Cascadia Mono',monospace;
      font-variant-numeric:tabular-nums;}

/* ---- masthead ---- */
.mast{display:flex; flex-wrap:wrap; align-items:flex-end; justify-content:space-between;
      gap:16px; padding-bottom:20px; border-bottom:2px solid var(--ink);}
.mast .sub{color:var(--muted); font-size:14px; margin-top:6px;}
.stamp{font-size:12.5px; color:var(--muted); text-align:right; line-height:1.7;}

.verdict{
  margin:24px 0 0; padding:18px 22px; border-radius:3px;
  background:var(--surface); border:1px solid var(--line);
  border-left:4px solid var(--accent);
  display:flex; flex-wrap:wrap; gap:8px 28px; align-items:baseline;
}
.verdict b{font-family:'Archivo','Noto Sans KR',sans-serif; font-size:17px;}
.verdict span{color:var(--ink-2); font-size:14px;}

section{margin-top:44px;}
.head{display:flex; align-items:baseline; justify-content:space-between; gap:16px;
      margin-bottom:14px;}
.head .note{font-size:12.5px; color:var(--muted);}

/* ---- roster ---- */
.roster{display:flex; flex-direction:column; gap:2px;
        background:var(--line); border:1px solid var(--line); border-radius:3px;
        overflow:hidden;}
.row{background:var(--surface); padding:16px 20px 16px 17px; border-left:3px solid var(--st);
     display:grid; grid-template-columns:minmax(0,1fr) auto; gap:4px 20px; align-items:start;}
.row .who{font-family:'Archivo','Noto Sans KR',sans-serif; font-weight:600; font-size:16px;}
.row .role{color:var(--muted); font-size:12.5px; letter-spacing:0.04em;}
.row .detail{grid-column:1/-1; color:var(--ink-2); font-size:14px; margin-top:4px;}
.row .ev{grid-column:1/-1; margin-top:8px; display:flex; flex-wrap:wrap; gap:6px;
         align-items:center;}
.ev .k{font-size:11px; letter-spacing:0.1em; text-transform:uppercase; color:var(--muted);}
.ev code{font-size:11.5px; padding:2px 7px; border-radius:2px;
         background:var(--sunk); color:var(--ink-2);}
.ev .none{font-size:11.5px; color:var(--blocked);}

.pill{display:inline-flex; align-items:center; gap:7px; white-space:nowrap;
      font-size:12px; font-weight:600; letter-spacing:0.05em;
      padding:4px 11px; border-radius:2px; background:var(--st-soft); color:var(--st);}
.pill::before{content:""; width:6px; height:6px; border-radius:50%; background:currentColor;}
.ver{font-size:12px; color:var(--muted); text-align:right; margin-top:3px;}

.s-ready{--st:var(--ok); --st-soft:var(--ok-soft);}
.s-gated{--st:var(--gate); --st-soft:var(--gate-soft);}
.s-blocked{--st:var(--blocked); --st-soft:var(--blocked-soft);}
.s-unknown{--st:var(--unknown); --st-soft:var(--unknown-soft);}

/* ---- board ---- */
.board{display:grid; grid-template-columns:repeat(auto-fit,minmax(320px,1fr)); gap:18px;}
.lane{background:var(--surface); border:1px solid var(--line); border-radius:3px;
      padding:18px 20px 20px;}
.lane > h3{font-size:13px; letter-spacing:0.1em; text-transform:uppercase;
           color:var(--muted); margin-bottom:14px;
           display:flex; justify-content:space-between; align-items:baseline;}
.lane .count{font-size:12px; color:var(--muted); letter-spacing:0;}
.task{padding:11px 0; border-top:1px solid var(--line);}
.task:first-of-type{border-top:0; padding-top:0;}
.task .t{display:flex; gap:10px; align-items:baseline; justify-content:space-between;}
.task .id{font-size:11.5px; color:var(--muted); letter-spacing:0.05em;}
.task .title{font-weight:500; font-size:14.5px;}
/* Wraps rather than scrolls: a clipped path with a hidden scrollbar reads as
   a broken layout, and only the filename identifies the file anyway. */
.task .files{margin-top:5px; font-size:11.5px; color:var(--muted); line-height:1.7;}
.tag{font-size:11px; font-weight:600; letter-spacing:0.05em; padding:2px 8px;
     border-radius:2px; background:var(--st-soft); color:var(--st); white-space:nowrap;}
.s-todo{--st:var(--unknown); --st-soft:var(--unknown-soft);}
.s-in_progress{--st:var(--accent); --st-soft:var(--accent-soft);}
.s-review{--st:var(--gate); --st-soft:var(--gate-soft);}
.s-done{--st:var(--ok); --st-soft:var(--ok-soft);}
.s-blocked-tag{--st:var(--blocked); --st-soft:var(--blocked-soft);}

/* ---- pipeline + facts ---- */
.grid2{display:grid; grid-template-columns:repeat(auto-fit,minmax(300px,1fr)); gap:18px;}
.panel{background:var(--surface); border:1px solid var(--line); border-radius:3px;
       padding:18px 20px 20px;}
.panel h3{font-size:13px; letter-spacing:0.1em; text-transform:uppercase;
          color:var(--muted); margin-bottom:14px;}
.kv{display:flex; justify-content:space-between; gap:16px; padding:8px 0;
    border-top:1px solid var(--line); font-size:14px;}
.kv:first-of-type{border-top:0;}
.kv .k{color:var(--muted);}
.kv .v{text-align:right; word-break:break-all;}
.big{font-family:'Archivo',sans-serif; font-size:15px; font-weight:600;}

/* ---- games ---- */
.games{display:flex; gap:5px; flex-wrap:wrap;}
.g{flex:1 1 84px; min-width:84px; border:1px solid var(--line); border-radius:2px;
   background:var(--surface); padding:11px 12px 12px; border-top:3px solid var(--st);}
.g .n{font-family:'Archivo',sans-serif; font-weight:700; font-size:14px;}
.g .s{font-size:11px; color:var(--st); margin-top:2px; font-weight:600;}
.g-done{--st:var(--ok);}
.g-active{--st:var(--accent);}
.g-todo{--st:var(--line);}
.g-todo .s{color:var(--muted); font-weight:400;}

/* ---- log ---- */
.log{background:var(--surface); border:1px solid var(--line); border-radius:3px;
     overflow:hidden;}
.log div{display:grid; grid-template-columns:auto auto minmax(0,1fr); gap:16px;
         padding:9px 20px; border-top:1px solid var(--line); font-size:13.5px;
         align-items:baseline;}
.log div:first-child{border-top:0;}
.log .sha{color:var(--accent);}
.log .when{color:var(--muted); font-size:12.5px;}
.log .what{overflow:hidden; text-overflow:ellipsis; white-space:nowrap;}

.warn{margin-top:14px; padding:14px 18px; border-radius:3px;
      background:var(--blocked-soft); border-left:4px solid var(--blocked);
      color:var(--ink); font-size:13.5px;}
.warn code{font-size:12.5px;}

footer{margin-top:52px; padding-top:18px; border-top:1px solid var(--line);
       color:var(--muted); font-size:12.5px; line-height:1.8;}
footer code{font-size:12px; background:var(--sunk); padding:2px 6px; border-radius:2px;}

@media (max-width:560px){
  h1{font-size:24px;}
  .wrap{padding:24px 16px 56px;}
  .stamp{text-align:left;}
  .log div{grid-template-columns:auto minmax(0,1fr); }
  .log .when{grid-column:1/-1;}
}
"""


def _agent_row(agent: Agent) -> str:
    evidence = (
        "".join(f"<code>{e(path)}</code>" for path in agent.evidence)
        if agent.evidence else '<span class="none">근거 없음 - 확인된 파일이 없습니다</span>'
    )
    version = f'<div class="ver mono">{e(agent.version)}</div>' if agent.version else ""
    return f"""      <div class="row s-{agent.state}">
        <div>
          <div class="who">{e(agent.name)}</div>
          <div class="role">{e(agent.role)}</div>
        </div>
        <div style="text-align:right">
          <span class="pill">{e(STATE_LABEL[agent.state])}</span>
          {version}
        </div>
        <div class="detail">{e(agent.detail)}</div>
        <div class="ev"><span class="k">근거</span>{evidence}</div>
      </div>"""


def _short_path(pattern: str) -> str:
    """Just enough of an allowlist entry to recognise it.

    Full repo-relative paths are what the board stores and what the allowlist
    check needs, but four of them on a card is a wall of "Assets/GameFactory/"
    with the only distinguishing part off the right edge.
    """
    cleaned = pattern.replace("\\", "/").rstrip("/")
    tail = cleaned.rsplit("/", 1)[-1] if cleaned else pattern
    return f"{tail}/" if pattern.rstrip().endswith("/") else tail


def _task_row(task: dict[str, Any]) -> str:
    status = str(task.get("status", "todo"))
    css = "s-blocked-tag" if status == "blocked" else f"s-{status}"
    label = {"todo": "대기", "in_progress": "진행 중", "review": "검토 필요",
             "blocked": "막힘", "done": "완료"}.get(status, status)

    paths = task.get("files", []) or []
    files = " · ".join(_short_path(p) for p in paths[:4])
    if len(paths) > 4:
        files += f" 외 {len(paths) - 4}개"
    return f"""        <div class="task">
          <div class="t">
            <span class="title">{e(task.get('title', ''))}</span>
            <span class="tag {css}">{e(label)}</span>
          </div>
          <div class="id mono">{e(task.get('id', ''))}</div>
          <div class="files mono">{e(files)}</div>
        </div>"""


def render(snapshot: Snapshot) -> str:
    counts = {state: sum(1 for a in snapshot.agents if a.state == state)
              for state in (READY, GATED, BLOCKED, UNKNOWN)}

    roster = "\n".join(_agent_row(agent) for agent in snapshot.agents)

    lanes = []
    for owner, label in (("claude", "Claude"), ("codex", "Codex")):
        owned = [t for t in snapshot.tasks if t.get("owner") == owner]
        rows = "\n".join(_task_row(t) for t in owned) or \
            '<div class="task"><span class="files">배정된 작업이 없습니다.</span></div>'
        lanes.append(f"""      <div class="lane">
        <h3>{e(label)}<span class="count">{len(owned)}개</span></h3>
{rows}
      </div>""")

    if snapshot.builds:
        build_rows = "\n".join(
            f'        <div class="kv"><span class="k">{e(b["game"] or b["file"])}</span>'
            f'<span class="v"><span class="big">{e(b["size"])}</span><br>'
            f'<span class="mono" style="font-size:11.5px;color:var(--muted)">'
            f'sha256:{e(b["sha"])}</span></span></div>'
            for b in snapshot.builds)
        build_note = (f'<div class="kv"><span class="k">빌드 시각</span>'
                      f'<span class="v mono">{e(snapshot.builds[0]["built"])}</span></div>')
    else:
        build_rows = ('        <div class="kv"><span class="k">검증된 APK</span>'
                      '<span class="v">없음</span></div>')
        build_note = ""

    def _error_cell(label: str, key: str) -> str:
        # A count that was never parsed is NOT zero. Defaulting it to 0 here
        # would print a clean bill of health for a section the report does not
        # actually contain.
        if key not in snapshot.errors:
            return (f'<div class="kv"><span class="k">{e(label)}</span>'
                    f'<span class="v" style="color:var(--unknown)">확인 불가</span></div>')
        count = snapshot.errors[key]
        colour = "var(--blocked)" if count else "var(--ok)"
        return (f'<div class="kv"><span class="k">{e(label)}</span>'
                f'<span class="v big" style="color:{colour}">{count}</span></div>')

    error_rows = "".join(_error_cell(label, key) for label, key in (
        ("컴파일 에러", "compile"),
        ("Obsolete API 경고", "obsolete"),
        ("런타임 예외", "runtime"),
    ))

    game_cells = "\n".join(
        f'      <div class="g g-{g["state"]}"><div class="n">{e(g["id"][4:])}</div>'
        f'<div class="s">{e({"done": "완료", "active": "진행 중", "todo": "미착수"}[g["state"]])}</div></div>'
        for g in snapshot.games)
    done_games = sum(1 for g in snapshot.games if g["state"] == "done")

    log = "\n".join(
        f'      <div><span class="sha mono">{e(c["sha"])}</span>'
        f'<span class="when mono">{e(c["date"])}</span>'
        f'<span class="what">{e(c["subject"])}</span></div>'
        for c in snapshot.commits) or '      <div><span class="what">git 기록을 읽지 못했습니다.</span></div>'

    # Plain ink, not the muted key colour: these ARE the content of the panel,
    # not labels for something else sitting beside them.
    gates = snapshot.policy.get("human_gates", [])
    gate_items = "".join(
        f'<div class="kv"><span class="v mono" style="text-align:left">{e(g)}</span></div>'
        for g in gates) or \
        '<div class="kv"><span class="k">정책 파일에 human_gates 가 없습니다.</span></div>'

    missing_block = ""
    if snapshot.missing:
        files = "".join(f"<code>{e(path)}</code> " for path in snapshot.missing)
        missing_block = (f'<div class="warn"><b>읽지 못한 파일이 있습니다.</b> {files}<br>'
                         "그만큼 이 페이지의 상태는 비어 있거나 '확인 불가'로 표시됩니다 - "
                         "빈 칸을 정상으로 바꿔 읽지 마세요.</div>")

    machine = snapshot.profile.get("machineName", "?")
    hardware = snapshot.profile.get("hardware", {})
    unity = snapshot.profile.get("unity", {})

    return f"""<title>Game Factory 관제</title>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Archivo:wght@400;600;700&family=Noto+Sans+KR:wght@400;500;700&family=JetBrains+Mono:wght@400;500&display=swap">
<style>{CSS}</style>

<div class="wrap">
  <header class="mast">
    <div>
      <h1>Game Factory 관제</h1>
      <div class="sub">연동된 AI가 지금 무엇을 할 수 있고, 무엇이 막고 있는가</div>
    </div>
    <div class="stamp mono">
      생성 {e(snapshot.generated_at)}<br>
      {e(machine)} · RAM {e(f"{hardware.get('ramTotalGb', 0):.1f}")} GB<br>
      Unity {e(unity.get('requiredByProject', '?'))} · {e(unity.get('status', '?'))}
    </div>
  </header>

  <div class="verdict">
    <b>{counts[READY]}개 작업 가능</b>
    <span>{counts[GATED]}개 대기 · {counts[BLOCKED]}개 사용 불가 · {counts[UNKNOWN]}개 확인 불가</span>
    <span>설치된 것과 실제로 돌아가는 것은 다릅니다. 아래 각 줄은 그 판단의 근거 파일을 함께 표시합니다.</span>
  </div>
  {missing_block}

  <section>
    <div class="head">
      <h2>연동된 AI</h2>
      <span class="note">근거 = 이 상태를 읽어온 파일</span>
    </div>
    <div class="roster">
{roster}
    </div>
  </section>

  <section>
    <div class="head">
      <h2>공유 작업판</h2>
      <span class="note">AI_GAME_COMPANY/config/TASKBOARD.json · 완료는 빌드 통과 후 사람이 정합니다</span>
    </div>
    <div class="board">
{chr(10).join(lanes)}
    </div>
  </section>

  <section>
    <div class="head">
      <h2>파이프라인</h2>
      <span class="note">디스크의 실제 파일만 셉니다</span>
    </div>
    <div class="grid2">
      <div class="panel">
        <h3>검증된 빌드</h3>
{build_rows}
        {build_note}
        <div class="kv"><span class="k">리포트 시각</span>
          <span class="v mono">{e(snapshot.build_report_at or '없음')}</span></div>
      </div>
      <div class="panel">
        <h3>Unity 에러</h3>
        {error_rows}
        <div class="kv"><span class="k">리포트 시각</span>
          <span class="v mono">{e(snapshot.error_report_at or '없음')}</span></div>
      </div>
    </div>
  </section>

  <section>
    <div class="head">
      <h2>10개 게임</h2>
      <span class="note">{done_games} / {len(snapshot.games)} 완료 · 리포트와 실제 APK가 둘 다 있어야 완료</span>
    </div>
    <div class="games">
{game_cells}
    </div>
  </section>

  <section>
    <div class="head"><h2>최근 작업</h2></div>
    <div class="log mono">
{log}
    </div>
  </section>

  <section>
    <div class="head">
      <h2>사람만 할 수 있는 일</h2>
      <span class="note">이 목록에 없는 것은 자동으로 진행합니다</span>
    </div>
    <div class="panel">
      {gate_items}
    </div>
  </section>

  <footer>
    이 페이지는 <code>python -m company.orchestrator.main dashboard</code> 로 다시 생성합니다.
    저장소에 커밋된 파일만 읽으므로 네트워크나 장비를 건드리지 않고, 빌드 PC에서든
    Unity를 본 적 없는 컨테이너에서든 같은 답을 냅니다.<br>
    빈 칸은 "이상 없음"이 아니라 "확인된 근거가 없음"입니다.
  </footer>
</div>
"""


def write(repo_root: Path, out_path: Path | None = None) -> Path:
    target = out_path or (repo_root / "Reports" / "dashboard.html")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(render(collect(repo_root)), encoding="utf-8")
    return target
