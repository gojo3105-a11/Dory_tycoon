"""Machine checks that stand in for "the AI said it was done" (sections 14, 32).

Every function returns a dict with `ok` plus the evidence used, so the result
can be attached to a task as acceptance evidence.
"""
from __future__ import annotations

import json
import re
import zipfile
from pathlib import Path
from typing import Any

from . import paths, process_runner


def file_exists(path: Path | str, *, min_bytes: int = 1) -> dict[str, Any]:
    p = Path(path)
    exists = p.exists()
    size = p.stat().st_size if exists and p.is_file() else 0
    return {
        "check": "file_exists",
        "path": str(p),
        "exists": exists,
        "size_bytes": size,
        "min_bytes": min_bytes,
        "ok": exists and size >= min_bytes,
    }


def json_parses(path: Path | str) -> dict[str, Any]:
    p = Path(path)
    result: dict[str, Any] = {"check": "json_parses", "path": str(p), "ok": False}
    if not p.exists():
        result["error"] = "missing"
        return result
    try:
        json.loads(p.read_text(encoding="utf-8"))
        result["ok"] = True
    except (json.JSONDecodeError, OSError) as exc:
        result["error"] = str(exc)
    return result


def all_files_exist(paths_list: list[Path | str], *, min_bytes: int = 1) -> dict[str, Any]:
    checks = [file_exists(p, min_bytes=min_bytes) for p in paths_list]
    return {
        "check": "all_files_exist",
        "count": len(checks),
        "missing": [c["path"] for c in checks if not c["ok"]],
        "ok": all(c["ok"] for c in checks) and bool(checks),
        "details": checks,
    }


def text_contains_no_errors(text: str, *,
                            patterns: tuple[str, ...] = (
                                r"^\s*SCRIPT ERROR",
                                r"^\s*ERROR:",
                                r"Parse Error",
                                r"error CS\d+",
                                r"Compilation failed",
                                r"Traceback \(most recent call last\)",
                            )) -> dict[str, Any]:
    hits: list[str] = []
    for line in (text or "").splitlines():
        for pattern in patterns:
            if re.search(pattern, line, re.IGNORECASE if pattern.startswith("Parse") else 0):
                hits.append(line.strip()[:300])
                break
    return {
        "check": "text_contains_no_errors",
        "error_lines": hits[:50],
        "error_count": len(hits),
        "ok": not hits,
    }


def apk_valid(apk_path: Path | str, *,
              expected_package: str | None = None) -> dict[str, Any]:
    """APK acceptance (section 32). No APK on disk means no completion."""
    p = Path(apk_path)
    result: dict[str, Any] = {
        "check": "apk_valid", "path": str(p), "exists": p.exists(),
        "size_bytes": p.stat().st_size if p.exists() and p.is_file() else 0,
        "is_zip": False, "has_manifest": False, "package_name": None,
        "package_name_source": None, "ok": False, "human_gate": None,
    }
    if not result["exists"] or result["size_bytes"] <= 0:
        result["error"] = "APK missing or empty"
        return result
    try:
        with zipfile.ZipFile(p) as zf:
            names = zf.namelist()
            result["is_zip"] = True
            result["has_manifest"] = "AndroidManifest.xml" in names
            result["entry_count"] = len(names)
            result["has_dex"] = any(n.endswith(".dex") for n in names)
    except zipfile.BadZipFile as exc:
        result["error"] = f"not a valid zip/apk: {exc}"
        return result

    if process_runner.which("aapt"):
        out = process_runner.run(["aapt", "dump", "badging", str(p)], timeout=120)
        match = re.search(r"package: name='([^']+)'", out.stdout or "")
        if match:
            result["package_name"] = match.group(1)
            result["package_name_source"] = "aapt"
    if result["package_name"] is None:
        result["human_gate"] = ("aapt not installed: package name could not be verified "
                                "automatically (section 32 HUMAN_GATE)")

    result["ok"] = bool(result["is_zip"] and result["has_manifest"]
                        and result["size_bytes"] > 0)
    if expected_package and result["package_name"]:
        result["package_matches"] = result["package_name"] == expected_package
        result["ok"] = result["ok"] and result["package_matches"]
    return result


def godot_project_valid(project_root: Path | str | None = None) -> dict[str, Any]:
    """Static structure check for a Godot project - no engine binary needed."""
    root = Path(project_root or paths.target_project_root())
    result: dict[str, Any] = {"check": "godot_project_valid", "root": str(root),
                              "ok": False, "problems": []}
    project_file = root / "project.godot"
    if not project_file.exists():
        result["problems"].append("project.godot missing")
        return result
    text = project_file.read_text(encoding="utf-8", errors="replace")
    result["config_name"] = _ini_value(text, "config/name")
    result["main_scene"] = _ini_value(text, "run/main_scene")
    result["features"] = _ini_value(text, "config/features")

    main_scene = (result["main_scene"] or "").strip('"')
    if main_scene.startswith("res://"):
        scene_path = root / main_scene[len("res://"):]
        if not scene_path.exists():
            result["problems"].append(f"main scene not found on disk: {main_scene}")
    elif main_scene:
        result["problems"].append(f"main scene is not a res:// path: {main_scene}")
    else:
        result["problems"].append("run/main_scene not set")

    # Every res:// reference inside scene/resource files must resolve.
    broken: list[str] = []
    for pattern in ("**/*.tscn", "**/*.tres"):
        for f in root.glob(pattern):
            if ".godot" in f.parts:
                continue
            body = f.read_text(encoding="utf-8", errors="replace")
            for ref in re.findall(r'res://[^"\')\s]+', body):
                target = root / ref[len("res://"):]
                if not target.exists():
                    broken.append(f"{f.relative_to(root)} -> {ref}")
    result["broken_resource_refs"] = broken[:50]
    if broken:
        result["problems"].append(f"{len(broken)} unresolved res:// reference(s)")

    result["scene_count"] = len([f for f in root.glob("**/*.tscn") if ".godot" not in f.parts])
    result["script_count"] = len([f for f in root.glob("**/*.gd") if ".godot" not in f.parts])
    result["ok"] = not result["problems"]
    return result


def _ini_value(text: str, key: str) -> str | None:
    match = re.search(rf"^{re.escape(key)}=(.+)$", text, re.MULTILINE)
    return match.group(1).strip() if match else None


def summarize(checks: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "acceptance_checked": True,
        "checks": checks,
        "failed": [c.get("check") for c in checks if not c.get("ok")],
        "ok": all(c.get("ok") for c in checks) and bool(checks),
    }
