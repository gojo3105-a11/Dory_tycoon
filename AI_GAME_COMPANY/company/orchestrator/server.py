"""A localhost control panel for the orchestrator.

WHY A SERVER AND NOT JUST THE HTML FILE. The dashboard can only ever describe
things; a page that runs Codex or starts an Android build has to be able to
execute something, and a published Artifact never can. So the read-only page
stays a file, and this serves the same page plus buttons - on the machine
where the AI tooling actually lives.

The buttons run commands, so this is the most dangerous file in the project.
Four rules hold, and all four are enforced here rather than documented:

  LOOPBACK ONLY
      Bound to 127.0.0.1. Never 0.0.0.0 - that would put a
      run-arbitrary-builds endpoint on whatever network the PC is joined to.

  NO COMMAND COMES FROM THE CLIENT
      The browser sends an action NAME. This file owns the argv. There is no
      code path where text from a request reaches a shell, and shell=False
      everywhere, so a crafted argument cannot become a second command.

  A TOKEN, BECAUSE LOCALHOST IS NOT A BOUNDARY
      Any page in the user's browser can POST to 127.0.0.1. A random
      per-run token, printed in the terminal and embedded only in the page
      this server itself renders, is what stops a hostile site firing a
      build. Requests carrying a foreign Origin are refused outright.

  ONE JOB AT A TIME
      These jobs are Unity builds and Codex runs against one working tree.
      Two at once would corrupt each other's results.

It commits nothing and pushes nothing: same rule as everywhere else, a person
reviews the diff.
"""

from __future__ import annotations

import json
import re
import secrets
import subprocess
import sys
import threading
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from company.orchestrator import dashboard as dash
from company.orchestrator.teamwork import TaskBoard

LOOPBACK = "127.0.0.1"
MAX_BODY = 8192
# Kept small and read-only-ish per entry; the log a browser polls does not
# need to hold a whole Gradle run.
MAX_LOG_CHARS = 200_000

# Ids we are willing to put on a command line. Anything else is rejected
# before argv is built, so the allowlist below never has to trust its input.
SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")


@dataclass
class Action:
    """One thing a button may do. argv is built here, never received."""
    label: str
    build: Any                      # (repo_root, arg) -> list[str]
    needs: str = ""                 # "" | "task" | "game"
    timeout: int = 900


def _python() -> str:
    """This interpreter, so a venv is not silently swapped for the system one."""
    return sys.executable or "python"


ACTIONS: dict[str, Action] = {
    "dashboard": Action(
        "대시보드 새로고침",
        lambda root, arg: [_python(), "-m", "company.orchestrator.main", "dashboard"],
        timeout=300),
    "codex-doctor": Action(
        "Codex 진단",
        lambda root, arg: [_python(), "-m", "company.orchestrator.main", "codex", "--doctor"],
        timeout=180),
    "team-run": Action(
        "Codex 작업 실행",
        lambda root, arg: [_python(), "-m", "company.orchestrator.main",
                           "team", "run", "--task", arg],
        needs="task", timeout=2400),
    "build": Action(
        "빌드",
        lambda root, arg: [_python(), "-m", "company.orchestrator.main",
                           "build", "--game", arg],
        needs="game", timeout=5400),
    "git-status": Action(
        "변경된 파일",
        lambda root, arg: ["git", "status", "--short", "--untracked-files=all"],
        timeout=60),
}


@dataclass
class Job:
    id: str
    action: str
    argv: list[str]
    output: str = ""
    done: bool = False
    exit_code: int | None = None
    lock: threading.Lock = field(default_factory=threading.Lock)

    def append(self, text: str) -> None:
        with self.lock:
            self.output += text
            if len(self.output) > MAX_LOG_CHARS:
                # Keep the tail: the failure is at the end of a build log.
                self.output = "...(앞부분 생략)...\n" + self.output[-MAX_LOG_CHARS:]

    def snapshot(self) -> dict[str, Any]:
        with self.lock:
            return {"job": self.id, "action": self.action, "output": self.output,
                    "done": self.done, "exit_code": self.exit_code}


class Runner:
    """Runs one job at a time and keeps only the current one's output."""

    def __init__(self, repo_root: Path, company_root: Path):
        self.repo_root = repo_root
        self.company_root = company_root
        self.lock = threading.Lock()
        self.current: Job | None = None

    def busy(self) -> bool:
        with self.lock:
            return self.current is not None and not self.current.done

    def valid_arg(self, action: Action, arg: str) -> tuple[bool, str]:
        """Is this id real, and is it safe to put on a command line?"""
        if not action.needs:
            return True, ""
        if not SAFE_ID.match(arg or ""):
            return False, "허용되지 않는 형식의 id 입니다."

        if action.needs == "task":
            board = TaskBoard.load(self.company_root / "config" / "TASKBOARD.json")
            ids = {t.id for t in board.tasks if t.owner == "codex"}
            if arg not in ids:
                return False, f"작업판에 Codex 소유의 '{arg}' 작업이 없습니다."
        elif action.needs == "game":
            if not (self.repo_root / "GameSpecs" / f"{arg}.json").is_file():
                return False, f"GameSpecs/{arg}.json 이 없습니다."
        return True, ""

    def start(self, name: str, arg: str) -> tuple[Job | None, str]:
        action = ACTIONS.get(name)
        if action is None:
            return None, "알 수 없는 동작입니다."

        ok, why = self.valid_arg(action, arg)
        if not ok:
            return None, why

        with self.lock:
            if self.current is not None and not self.current.done:
                return None, f"이미 '{self.current.action}' 이 실행 중입니다. 끝나면 다시 누르세요."

            job = Job(id=secrets.token_hex(8), action=name,
                      argv=action.build(self.repo_root, arg))
            self.current = job

        thread = threading.Thread(target=self._run, args=(job, action), daemon=True)
        thread.start()
        return job, ""

    def _run(self, job: Job, action: Action) -> None:
        # git runs at the repo root; the orchestrator module runs from
        # AI_GAME_COMPANY, which is where its package lives.
        cwd = self.repo_root if job.argv[0] == "git" else self.company_root
        job.append(f"$ {' '.join(job.argv)}\n\n")

        try:
            # shell=False: argv is a list this file built, so nothing in a
            # request can turn into a second command.
            process = subprocess.Popen(
                job.argv, cwd=str(cwd), stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT, text=True, bufsize=1,
                encoding="utf-8", errors="replace",
            )
        except OSError as exc:
            job.append(f"실행할 수 없습니다: {exc}\n")
            with job.lock:
                job.done, job.exit_code = True, -1
            return

        def reap() -> None:
            try:
                process.wait(timeout=action.timeout)
            except subprocess.TimeoutExpired:
                process.kill()
                job.append(f"\n{action.timeout}초를 넘겨 중단했습니다.\n")

        timer = threading.Thread(target=reap, daemon=True)
        timer.start()

        if process.stdout is not None:
            # closing() rather than a bare loop: a build can be killed by the
            # timeout above while this is mid-read, and the pipe would then be
            # left open for the life of the server.
            with process.stdout as stream:
                for line in stream:
                    job.append(line)
        code = process.wait()

        with job.lock:
            job.done, job.exit_code = True, code


class Handler(BaseHTTPRequestHandler):
    server_version = "GameFactoryControl/1"
    runner: Runner
    token: str

    # ---- plumbing ----

    def log_message(self, fmt: str, *args: Any) -> None:
        """Quiet by default: the terminal is where job output belongs."""

    def _send(self, code: int, body: bytes, content_type: str) -> None:
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        # This page inlines its own script and its images as data URIs, and
        # must never be framed by another site.
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.end_headers()
        self.wfile.write(body)

    def _json(self, code: int, payload: dict[str, Any]) -> None:
        self._send(code, json.dumps(payload, ensure_ascii=False).encode("utf-8"),
                   "application/json; charset=utf-8")

    def _local_host(self) -> bool:
        """Host header must name this loopback server, not a public name."""
        host = (self.headers.get("Host") or "").split(":")[0].strip("[]")
        return host in (LOOPBACK, "localhost", "::1")

    def _origin_ok(self) -> bool:
        """A cross-site POST is refused. Same-origin requests send no Origin
        or one matching us; a hostile page always sends its own."""
        origin = self.headers.get("Origin")
        if not origin:
            return True
        return origin.split("://")[-1].split(":")[0].strip("[]") in (
            LOOPBACK, "localhost", "::1")

    # ---- routes ----

    def do_GET(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler's name
        if not self._local_host():
            self._json(400, {"error": "bad host"})
            return

        if self.path.startswith("/log"):
            self._log()
            return
        if self.path in ("/", "/index.html"):
            snapshot = dash.collect(self.runner.repo_root)
            page = dash.render(snapshot, control_token=self.token)
            self._send(200, dash.standalone(page).encode("utf-8"),
                       "text/html; charset=utf-8")
            return

        self._json(404, {"error": "not found"})

    def _log(self) -> None:
        job = self.runner.current
        wanted = ""
        if "?" in self.path:
            for pair in self.path.split("?", 1)[1].split("&"):
                key, _, value = pair.partition("=")
                if key == "job":
                    wanted = value
        if job is None or (wanted and wanted != job.id):
            self._json(404, {"error": "그 작업의 로그가 없습니다.", "done": True,
                             "exit_code": -1, "output": ""})
            return
        self._json(200, job.snapshot())

    def do_POST(self) -> None:  # noqa: N802
        if not self._local_host():
            self._json(400, {"error": "bad host"})
            return
        if not self._origin_ok():
            self._json(403, {"error": "cross-site 요청은 거부됩니다."})
            return
        if self.path != "/run":
            self._json(404, {"error": "not found"})
            return

        try:
            length = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            self._json(400, {"error": "bad length"})
            return
        if length <= 0 or length > MAX_BODY:
            self._json(400, {"error": "bad body size"})
            return

        try:
            payload = json.loads(self.rfile.read(length).decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            self._json(400, {"error": "bad json"})
            return
        if not isinstance(payload, dict):
            self._json(400, {"error": "bad json"})
            return

        # compare_digest, so a wrong token cannot be found one character at a
        # time by timing the responses.
        if not secrets.compare_digest(str(payload.get("token", "")), self.token):
            self._json(403, {"error": "토큰이 맞지 않습니다. 터미널에 찍힌 주소로 다시 여세요."})
            return

        job, why = self.runner.start(str(payload.get("action", "")),
                                     str(payload.get("arg", "")))
        if job is None:
            self._json(409, {"error": why})
            return

        print(f"  [실행] {' '.join(job.argv)}")
        self._json(200, {"job": job.id})


def make_handler(runner: Runner, token: str) -> type[Handler]:
    """Bind a runner and token to a handler class.

    BaseHTTPRequestHandler is instantiated per request by the server, so
    per-server state has to live on the class. Split out from serve() so a
    test can stand up a real server without serve()'s printing and blocking.
    """
    return type("BoundHandler", (Handler,), {"runner": runner, "token": token})


def serve(repo_root: Path, company_root: Path, port: int = 8765) -> int:
    """Run the control panel until interrupted. Returns a process exit code."""
    token = secrets.token_urlsafe(24)
    handler = make_handler(Runner(repo_root, company_root), token)

    try:
        # ThreadingHTTPServer: a job polls /log while it runs, so a
        # single-threaded server would block on its own long request.
        httpd = ThreadingHTTPServer((LOOPBACK, port), handler)
    except OSError as exc:
        print(f"ERROR: {LOOPBACK}:{port} 를 열 수 없습니다 - {exc}")
        print("  이미 실행 중이거나 다른 프로그램이 쓰고 있습니다. --port 로 바꿔보세요.")
        return 2

    url = f"http://{LOOPBACK}:{port}/"
    print("=== GAME FACTORY 제어판 ===")
    print(f"  {url}")
    print(f"  이 주소는 이 PC에서만 열립니다 ({LOOPBACK} 전용).")
    print("  실행 가능한 동작: " + ", ".join(ACTIONS))
    print("  커밋과 푸시는 하지 않습니다. Ctrl+C 로 종료합니다.\n")

    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n종료합니다.")
    finally:
        httpd.server_close()
    return 0
