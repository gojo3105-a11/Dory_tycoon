"""HARDWARE_PROFILE.json generator (master prompt sections 6, STEP 3-4).

Cross-platform, stdlib only. Everything is measured, never assumed, and the
model recommendation is derived from what the machine can actually run rather
than always reaching for the largest model.
"""
from __future__ import annotations

import json
import os
import platform
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from . import paths, process_runner
from .policy import Policy

# Programs the master prompt asks us to detect (STEP 4), plus the Godot
# toolchain this repository actually uses.
DETECT_TARGETS: list[tuple[str, tuple[str, ...]]] = [
    ("python3", ("--version",)),
    ("git", ("--version",)),
    ("node", ("--version",)),
    ("npm", ("--version",)),
    ("java", ("-version",)),
    ("javac", ("-version",)),
    ("gradle", ("--version",)),
    ("claude", ("--version",)),
    ("codex", ("--version",)),
    ("ollama", ("--version",)),
    ("blender", ("--version",)),
    ("godot", ("--version",)),
    ("godot4", ("--version",)),
    ("unity", ("-version",)),
    ("adb", ("version",)),
    ("aapt", ("version",)),
    ("ffmpeg", ("-version",)),
]


def _ram_mb() -> dict[str, int | None]:
    total = free = None
    try:
        if hasattr(os, "sysconf") and "SC_PAGE_SIZE" in os.sysconf_names:
            page = os.sysconf("SC_PAGE_SIZE")
            if "SC_PHYS_PAGES" in os.sysconf_names:
                total = page * os.sysconf("SC_PHYS_PAGES") // (1024 * 1024)
            if "SC_AVPHYS_PAGES" in os.sysconf_names:
                free = page * os.sysconf("SC_AVPHYS_PAGES") // (1024 * 1024)
        meminfo = Path("/proc/meminfo")
        if meminfo.exists():
            values = {}
            for line in meminfo.read_text().splitlines():
                key, _, rest = line.partition(":")
                digits = "".join(ch for ch in rest if ch.isdigit())
                if digits:
                    values[key.strip()] = int(digits) // 1024
            total = values.get("MemTotal", total)
            free = values.get("MemAvailable", free)
    except OSError:
        pass
    if total is None and platform.system() == "Windows":
        result = process_runner.run(
            ["wmic", "ComputerSystem", "get", "TotalPhysicalMemory"], timeout=30)
        digits = "".join(ch for ch in result.stdout if ch.isdigit())
        if digits:
            total = int(digits) // (1024 * 1024)
    return {"total_mb": total, "free_mb": free}


def _gpu() -> dict[str, Any]:
    info: dict[str, Any] = {"detected": False, "name": None, "vram_mb": None,
                            "cuda": None, "source": None}
    if shutil.which("nvidia-smi"):
        result = process_runner.run(
            ["nvidia-smi", "--query-gpu=name,memory.total,driver_version",
             "--format=csv,noheader"], timeout=60)
        if result.ok and result.stdout.strip():
            first = result.stdout.strip().splitlines()[0]
            parts = [p.strip() for p in first.split(",")]
            info.update(detected=True, name=parts[0], source="nvidia-smi")
            if len(parts) > 1:
                digits = "".join(ch for ch in parts[1] if ch.isdigit())
                info["vram_mb"] = int(digits) if digits else None
            cuda = process_runner.run(["nvidia-smi"], timeout=60)
            if "CUDA Version" in cuda.stdout:
                info["cuda"] = cuda.stdout.split("CUDA Version:")[1].split()[0]
            return info
    if platform.system() == "Windows":
        result = process_runner.run(
            ["wmic", "path", "win32_VideoController", "get", "name"], timeout=30)
        names = [ln.strip() for ln in result.stdout.splitlines()[1:] if ln.strip()]
        if names:
            info.update(detected=True, name=names[0], source="wmic")
    elif platform.system() == "Darwin":
        result = process_runner.run(
            ["system_profiler", "SPDisplaysDataType"], timeout=60)
        for line in result.stdout.splitlines():
            if "Chipset Model:" in line:
                info.update(detected=True, name=line.split(":", 1)[1].strip(),
                            source="system_profiler")
                break
    return info


def _android_sdk() -> dict[str, Any]:
    candidates = [os.environ.get("ANDROID_HOME"), os.environ.get("ANDROID_SDK_ROOT")]
    home = Path.home()
    candidates += [
        str(home / "Android/Sdk"),
        str(home / "AppData/Local/Android/Sdk"),
        str(home / "Library/Android/sdk"),
    ]
    for c in candidates:
        if c and Path(c).expanduser().is_dir():
            root = Path(c).expanduser()
            return {
                "installed": True,
                "path": str(root),
                "platform_tools": (root / "platform-tools").is_dir(),
                "build_tools": sorted(p.name for p in (root / "build-tools").glob("*")) if (root / "build-tools").is_dir() else [],
                "status": "OK",
            }
    return {"installed": False, "path": None, "status": "MISSING"}


def _cli_capabilities() -> dict[str, Any]:
    """STEP 5: only record flags that the installed --help actually documents."""
    caps: dict[str, Any] = {}
    if shutil.which("claude"):
        caps["claude"] = {
            "print_mode": process_runner.supports_flag("claude", "--print"),
            "output_format": process_runner.supports_flag("claude", "--output-format"),
            "permission_mode": process_runner.supports_flag("claude", "--permission-mode"),
        }
    if shutil.which("codex"):
        caps["codex"] = {
            "exec": process_runner.supports_flag("codex", "exec"),
            "json": process_runner.supports_flag("codex", "--json"),
        }
    if shutil.which("blender"):
        caps["blender"] = {
            "background": process_runner.supports_flag("blender", "--background"),
            "python": process_runner.supports_flag("blender", "--python"),
        }
    return caps


def recommend_local_models(profile: dict[str, Any]) -> dict[str, Any]:
    """Pick the biggest candidate the machine can actually hold (section 5)."""
    ram_gb = (profile["ram"]["total_mb"] or 0) / 1024
    vram_gb = (profile["gpu"]["vram_mb"] or 0) / 1024
    registry_file = paths.MODEL_REGISTRY_FILE
    registry = json.loads(registry_file.read_text(encoding="utf-8")) if registry_file.exists() else {}
    picks: dict[str, Any] = {"ram_gb": round(ram_gb, 1), "vram_gb": round(vram_gb, 1),
                             "cpu_only": vram_gb < 4}
    for role in ("LOCAL_PLANNER", "LOCAL_REASONER"):
        fits = [
            m for m in registry.get("local_llm_candidates", [])
            if m.get("role") == role
            and ram_gb >= float(m.get("min_ram_gb", 0))
            and (vram_gb >= float(m.get("min_vram_gb", 0)) or float(m.get("min_vram_gb", 0)) == 0)
        ]
        fits.sort(key=lambda m: float(m.get("min_ram_gb", 0)), reverse=True)
        picks[role] = {
            "candidate": fits[0]["id"] if fits else None,
            "license_status": fits[0].get("license_status") if fits else None,
            "usable_in_production": bool(fits) and fits[0].get("license_status") == "APPROVED",
            "note": "license must be APPROVED before production use (section 8)",
        }
    picks["image_generation"] = {
        "candidate": None if vram_gb < 8 else "FLUX.1-schnell",
        "fallback": "procedural / existing licensed assets" if vram_gb < 8 else None,
        "reason": f"vram {vram_gb:.1f}GB",
    }
    picks["image_to_3d"] = {
        "candidate": None if vram_gb < 6 else "TripoSR",
        "fallback": "ROUTE B pre-rigged humanoid base (section 10)",
        "reason": f"vram {vram_gb:.1f}GB",
    }
    return picks


def build_profile(policy: Policy | None = None) -> dict[str, Any]:
    policy = policy or Policy.load()
    disk = shutil.disk_usage(str(paths.ROOT))
    profile: dict[str, Any] = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "profile_of": {
            "hostname": platform.node(),
            "note": "This file describes the machine that ran the profiler. "
                    "Re-run on each machine; do not copy between machines.",
        },
        "os": {
            "system": platform.system(),
            "release": platform.release(),
            "version": platform.version(),
            "machine": platform.machine(),
            "platform": platform.platform(),
        },
        "cpu": {
            "processor": platform.processor() or platform.machine(),
            "core_count": os.cpu_count(),
        },
        "ram": _ram_mb(),
        "gpu": _gpu(),
        "disk": {
            "root": str(paths.ROOT),
            "total_gb": round(disk.total / 1024**3, 1),
            "free_gb": round(disk.free / 1024**3, 1),
        },
        "python": {
            "version": sys.version.split()[0],
            "executable": sys.executable,
        },
        "programs": {},
        "android_sdk": _android_sdk(),
        "cli_capabilities": {},
    }
    for name, args in DETECT_TARGETS:
        profile["programs"][name] = process_runner.probe_version(name, args)
    profile["cli_capabilities"] = _cli_capabilities()
    profile["model_recommendation"] = recommend_local_models(profile)
    profile["warnings"] = _warnings(profile)
    return profile


def _warnings(profile: dict[str, Any]) -> list[str]:
    out = []
    if not profile["gpu"]["detected"]:
        out.append("No GPU detected: local image generation and image-to-3D "
                   "fall back to procedural / existing assets (section 6).")
    missing = [n for n, p in profile["programs"].items() if not p["installed"]]
    if missing:
        out.append("Not installed: " + ", ".join(missing))
    if (profile["ram"]["total_mb"] or 0) < 8192:
        out.append("Under 8GB RAM: use the smallest quantised local model only.")
    if profile["disk"]["free_gb"] < 20:
        out.append("Under 20GB free disk: model downloads and Android builds may fail.")
    return out


def write_profile(policy: Policy | None = None) -> tuple[Path, dict[str, Any]]:
    paths.ensure_dirs()
    profile = build_profile(policy)
    target = paths.HARDWARE_PROFILE_FILE
    target.write_text(json.dumps(profile, indent=2, ensure_ascii=False), encoding="utf-8")
    return target, profile
