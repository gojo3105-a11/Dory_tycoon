"""Drives Unity in batch mode. Master prompt section 18 and STEP 14.

DESIGN NOTE - why this does not call Unity.exe directly.

On Windows Unity can relaunch itself as a separate process, so the exit code
of the process we start is not the exit code of the work. Trusting it made
every CI step "succeed" in seconds while the real Unity run was later killed
as an orphan. scripts/ci/wait-for-unity.ps1 already solves this by waiting on
a Logs/<name>.exitcode sentinel that the Editor writes through CommandLineExit,
and that script is the one currently producing real APKs.

So this module builds the same invocations that workflow uses and delegates to
that script. Re-implementing the sentinel handling in Python would risk
reintroducing a bug that cost real debugging time, for no benefit.

The argument list is written into a generated .ps1 rather than passed on a
command line: Unity paths contain spaces ("C:\\Program Files\\..."), and
quoting a string[] through subprocess -> powershell.exe -File is a well known
source of silent breakage. A generated script with a proper PowerShell array
literal is deterministic, and it stays on disk so a failed run can be
inspected instead of guessed at.
"""

from __future__ import annotations

import subprocess
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path

from company.orchestrator.policy import Policy, PolicyViolation

# Verified against .github/workflows/game-factory.yml, which has produced a
# real APK on the self-hosted runner. Section 38: not invented.
ENTRY_GENERATE = "GameFactory.Editor.GameFactoryGenerator.GenerateFromCommandLine"
ENTRY_VALIDATE = "GameFactory.Editor.GameValidator.ValidateFromCommandLine"
ENTRY_BUILD = "GameFactory.Editor.BuildAndroid.BuildFromCommandLine"

WAIT_SCRIPT = Path("scripts") / "ci" / "wait-for-unity.ps1"


def ps_quote(value: str) -> str:
    """Single-quoted PowerShell literal; ' is escaped by doubling it."""
    return "'" + str(value).replace("'", "''") + "'"


@dataclass
class UnityResult:
    step: str
    exit_code: int | None
    ok: bool
    log_path: Path | None = None
    script_path: Path | None = None
    stdout: str = ""
    stderr: str = ""
    detail: str = ""


@dataclass
class UnityRunner:
    repo_root: Path
    policy: Policy
    timeout_minutes: int = 30
    # wait-for-unity.ps1 launches $env:UNITY_PATH. On the self-hosted runner
    # that is a machine environment variable, which is why the workflow never
    # sets it - and why a local run from an ordinary shell would launch nothing
    # at all. Passing it explicitly makes a local build self-sufficient instead
    # of depending on how the machine happens to be configured.
    unity_path: str | None = None
    # Injectable so the command construction can be tested without Windows.
    runner: object = field(default=None, repr=False)

    @staticmethod
    def unity_path_from_profile(profile_path: Path) -> str | None:
        """The editor path detect-environment.ps1 already verified."""
        if not profile_path.is_file():
            return None
        import json
        profile = json.loads(profile_path.read_text(encoding="utf-8-sig"))
        unity = profile.get("unity") or {}
        if unity.get("status") != "OK":
            return None
        return unity.get("matchingEditorPath") or None

    # ---- invocation building ---------------------------------------------

    def unity_args(self, entry_method: str, log_name: str,
                   extra: list[str] | None = None) -> list[str]:
        """The -batchmode argument list, matching the working workflow exactly."""
        args = [
            "-batchmode", "-nographics",
            "-projectPath", str(self.repo_root),
            "-executeMethod", entry_method,
        ]
        args += extra or []
        args += ["-logFile", str(self.repo_root / "Logs" / f"{log_name}.log")]
        return args

    def build_wrapper_script(self, sentinel_name: str, unity_args: list[str],
                             timeout_minutes: int | None = None) -> str:
        """The generated .ps1 that calls wait-for-unity.ps1."""
        quoted = ", ".join(ps_quote(a) for a in unity_args)
        timeout = timeout_minutes or self.timeout_minutes
        unity_line = ""
        if self.unity_path:
            unity_line = f"$env:UNITY_PATH = {ps_quote(self.unity_path)}\r\n"
        return (
            "$ErrorActionPreference = 'Stop'\r\n"
            f"{unity_line}"
            f"Set-Location {ps_quote(self.repo_root)}\r\n"
            f"& {ps_quote(self.repo_root / WAIT_SCRIPT)} "
            f"-SentinelName {ps_quote(sentinel_name)} "
            f"-TimeoutMinutes {int(timeout)} "
            f"-UnityArgs @({quoted})\r\n"
            "exit $LASTEXITCODE\r\n"
        )

    # ---- execution -------------------------------------------------------

    def _run_powershell(self, script_text: str,
                        timeout_minutes: int | None = None) -> tuple[int, str, str, Path]:
        scripts_dir = self.repo_root / "AI_GAME_COMPANY" / "logs" / "unity-invocations"
        scripts_dir.mkdir(parents=True, exist_ok=True)
        stamp = time.strftime("%Y%m%d-%H%M%S")
        script_path = scripts_dir / f"invoke-{stamp}-{uuid.uuid4().hex[:6]}.ps1"
        # ascii on purpose: PowerShell 5.1 reads a BOM-less UTF-8 .ps1 using
        # the local codepage, so a stray non-ASCII byte can break parsing.
        script_path.write_text(script_text, encoding="ascii")

        if self.runner is not None:  # test seam
            code, out, err = self.runner(script_path, script_text)
            return code, out, err, script_path

        # Must match what the generated script gave wait-for-unity.ps1, plus
        # slack. Using self.timeout_minutes here regardless meant the build step
        # allowed the inner script 60 minutes while killing the outer process at
        # 32 - so a cold Gradle cache produced an uncaught TimeoutExpired and
        # left Unity running detached.
        budget = timeout_minutes or self.timeout_minutes
        completed = subprocess.run(
            ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass",
             "-File", str(script_path)],
            capture_output=True, text=True,
            cwd=str(self.repo_root),
            timeout=budget * 60 + 120,
        )
        return completed.returncode, completed.stdout, completed.stderr, script_path

    def _step(self, step: str, sentinel: str, entry: str, log_name: str,
              extra: list[str] | None = None,
              timeout_minutes: int | None = None) -> UnityResult:
        args = self.unity_args(entry, log_name, extra)
        script = self.build_wrapper_script(sentinel, args, timeout_minutes)

        try:
            code, out, err, script_path = self._run_powershell(script, timeout_minutes)
        except subprocess.TimeoutExpired as exc:
            # A timeout is a failed step, not a crash. Say plainly that Unity
            # was launched detached and may still be running, because killing
            # powershell.exe does not kill it - that is the whole reason
            # wait-for-unity.ps1 waits on a sentinel instead of a process.
            minutes = timeout_minutes or self.timeout_minutes
            return UnityResult(
                step=step, exit_code=None, ok=False,
                log_path=self.repo_root / "Logs" / f"{log_name}.log",
                detail=(
                    f"{step} timed out after {minutes} min. Unity was started "
                    "detached, so it may still be running - check Task Manager "
                    f"and Logs/{log_name}.log before re-running."
                ),
                stderr=str(exc),
            )

        return UnityResult(
            step=step,
            exit_code=code,
            ok=(code == 0),
            log_path=self.repo_root / "Logs" / f"{log_name}.log",
            script_path=script_path,
            stdout=out,
            stderr=err,
            detail="" if code == 0 else f"{step} exited {code}",
        )

    def generate(self, game_id: str) -> UnityResult:
        return self._step(
            "generate", "generate", ENTRY_GENERATE, "unity-generate",
            extra=["-gameSpec", f"GameSpecs/{game_id}.json"],
        )

    def validate(self) -> UnityResult:
        return self._step("validate", "validate", ENTRY_VALIDATE, "unity-validate")

    def build_android(self, game_id: str) -> UnityResult:
        # 60 minutes because that is what the working workflow allows for the
        # build step; Gradle on a cold cache genuinely takes that long.
        return self._step(
            "build", "build", ENTRY_BUILD, "unity-build",
            extra=["-gameSpec", f"GameSpecs/{game_id}.json"],
            timeout_minutes=60,
        )

    # ---- verification ----------------------------------------------------

    def find_apk(self, game_id: str) -> Path | None:
        """A non-empty .apk/.aab under Builds/<game_id>/, newest first."""
        build_dir = self.repo_root / "Builds" / game_id
        if not build_dir.is_dir():
            return None
        found = [
            path for pattern in ("**/*.apk", "**/*.aab")
            for path in build_dir.glob(pattern)
            if path.is_file() and path.stat().st_size > 0
        ]
        if not found:
            return None
        return max(found, key=lambda p: p.stat().st_mtime)

    def verify_build(self, game_id: str, result: UnityResult) -> Path:
        """Sections 18 and 32: exit code AND build report AND APK on disk.

        Returns the APK path, or raises PolicyViolation. Deliberately raises
        rather than returning a bool - section 38 forbids reporting a build as
        successful without an APK, and an ignored return value is how that
        rule gets broken by accident.
        """
        apk = self.find_apk(game_id)
        report = self.repo_root / "Logs" / "unity-build.log"

        self.policy.assert_build_verification(
            exit_code_ok=result.ok,
            report_ok=report.is_file() and report.stat().st_size > 0,
            apk_exists=apk is not None,
        )
        assert apk is not None  # assert_build_verification raises otherwise
        return apk

    def run_pipeline(self, game_id: str) -> tuple[list[UnityResult], Path | None]:
        """generate -> validate -> build, stopping at the first failure.

        Mirrors the workflow's ordering. Tests are left to the workflow: it
        already runs EditMode and PlayMode through the same wrapper, and
        duplicating that here would mean two places to keep in sync.
        """
        results: list[UnityResult] = []

        for step in (self.generate(game_id), self.validate()):
            results.append(step)
            if not step.ok:
                return results, None

        build = self.build_android(game_id)
        results.append(build)
        if not build.ok:
            return results, None

        try:
            return results, self.verify_build(game_id, build)
        except PolicyViolation as exc:
            build.ok = False
            build.detail = str(exc)
            return results, None
