"""Reads HARDWARE_PROFILE.json and decides what this machine can actually run.

Master prompt sections 5 and 6: model size is chosen from the real machine,
never fixed in advance, and "do not download the largest model regardless".
Section 39 additionally requires that limits be reflected in the design
rather than hidden.

This module deliberately returns NOT_VIABLE verdicts. A pipeline that
schedules local image generation on an integrated GPU does not fail loudly -
it hangs for an hour and produces nothing, which is worse than being told up
front that the step is out of reach on this hardware.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

# Rough working-set costs, chosen to be honest rather than optimistic. A Q4
# quantised model needs its weights resident plus context and runtime slack.
LLM_TIERS = [
    # (label, approx GB needed, note)
    ("7b-q4", 6.0, "7B class, 4-bit quantised"),
    ("3b-q4", 3.0, "3B class, 4-bit quantised"),
    ("1.5b-q4", 1.8, "1.5B class, 4-bit quantised"),
]

# Local diffusion needs dedicated VRAM to be usable at all. Below this it
# falls back to CPU, where a single image is minutes-to-tens-of-minutes.
MIN_VRAM_GB_FOR_IMAGE_GEN = 6.0


@dataclass(frozen=True)
class Verdict:
    capability: str
    status: str  # VIABLE | LIMITED | NOT_VIABLE | UNKNOWN
    reason: str
    recommendation: str = ""


@dataclass(frozen=True)
class HardwareProfile:
    raw: dict[str, Any]
    source: Path | None = None

    @classmethod
    def load(cls, path: Path) -> "HardwareProfile":
        """Written by PowerShell's Set-Content -Encoding UTF8, so expect a BOM."""
        return cls(raw=json.loads(path.read_text(encoding="utf-8-sig")), source=path)

    # ---- raw facts -------------------------------------------------------

    @property
    def ram_total_gb(self) -> float:
        return float(self.raw.get("hardware", {}).get("ramTotalGb") or 0.0)

    @property
    def ram_free_gb(self) -> float:
        return float(self.raw.get("hardware", {}).get("ramFreeGb") or 0.0)

    @property
    def cpu(self) -> str:
        return str(self.raw.get("hardware", {}).get("cpu") or "unknown")

    @property
    def gpu_names(self) -> list[str]:
        return [str(g.get("name")) for g in self.raw.get("hardware", {}).get("gpus", [])]

    @property
    def has_dedicated_gpu(self) -> bool:
        """nvidia-smi answering is the only trustworthy signal we collect.

        Win32_VideoController's AdapterRAM is a uint32 that silently wraps
        above 4 GB, so it is recorded as a hint and not used for decisions.
        """
        return bool(self.raw.get("hardware", {}).get("nvidiaSmi", {}).get("available"))

    def tool(self, name: str) -> dict[str, Any]:
        return dict(self.raw.get("tools", {}).get(name) or {})

    def tool_installed(self, name: str) -> bool:
        return bool(self.tool(name).get("installed"))

    def tool_runnable(self, name: str) -> bool:
        """Installed AND its own --help/--version actually executed.

        The distinction is not pedantic: npm shim CLIs showed up as installed
        but unrunnable, which means no verified command list, which under
        section 41 STEP 5 means no adapter may be written for them.
        """
        return self.tool(name).get("status") == "OK"

    @property
    def ollama_reachable(self) -> bool:
        return bool(self.raw.get("ollamaApi", {}).get("reachable"))

    @property
    def ollama_models(self) -> list[str]:
        return [str(m.get("name")) for m in self.raw.get("ollamaApi", {}).get("models", [])]

    @property
    def ollama_model_sizes(self) -> list[tuple[str, float]]:
        """(model id, weight size in GB) for each installed model."""
        return [
            (str(m.get("name")), float(m.get("sizeGb") or 0.0))
            for m in self.raw.get("ollamaApi", {}).get("models", [])
        ]

    @property
    def unity_ok(self) -> bool:
        return self.raw.get("unity", {}).get("status") == "OK"

    @property
    def unity_editor_path(self) -> str | None:
        return self.raw.get("unity", {}).get("matchingEditorPath")

    # ---- decisions -------------------------------------------------------

    def recommend_llm_tier(self) -> tuple[str | None, str]:
        """Largest tier that fits in free RAM, with headroom for Unity.

        Budgets against FREE rather than total memory, and holds back 2 GB,
        because the whole point of the local model is to run alongside a Unity
        build - a model that only fits when nothing else runs is not usable.
        """
        budget = self.ram_free_gb - 2.0
        if budget <= 0:
            return None, (
                f"only {self.ram_free_gb:.1f} GB free - no room for a local model "
                "while leaving headroom for Unity"
            )

        for label, needed, note in LLM_TIERS:
            if needed <= budget:
                return label, (
                    f"{note}; needs about {needed:.1f} GB, budget is "
                    f"{budget:.1f} GB ({self.ram_free_gb:.1f} GB free minus 2 GB headroom)"
                )

        smallest_label, smallest_need, _ = LLM_TIERS[-1]
        return None, (
            f"even {smallest_label} wants about {smallest_need:.1f} GB but the budget "
            f"is only {budget:.1f} GB"
        )

    def model_fit(self, size_gb: float) -> tuple[str, str]:
        """Can a model of this weight size actually run here?

        Being downloaded is not the same as being runnable. Ollama will accept
        a pull far larger than the machine's memory and then either fail to
        load it or thrash to disk, which looks like a hang rather than an
        error - so the size is checked against real RAM before anything tries
        to use it.
        """
        if size_gb <= 0:
            return "UNKNOWN", "no size recorded for this model"

        if size_gb >= self.ram_total_gb:
            return "NOT_VIABLE", (
                f"{size_gb:.1f} GB of weights against {self.ram_total_gb:.1f} GB of "
                "total RAM - larger than the whole machine, so it cannot be loaded "
                "at all, whatever else is closed"
            )

        budget = self.ram_free_gb - 2.0
        if size_gb > budget:
            return "NOT_VIABLE", (
                f"{size_gb:.1f} GB of weights against a {budget:.1f} GB budget "
                f"({self.ram_free_gb:.1f} GB free minus 2 GB headroom) - it would "
                "swap to disk instead of running"
            )

        if not self.has_dedicated_gpu:
            return "LIMITED", (
                f"{size_gb:.1f} GB fits the {budget:.1f} GB budget, but inference is "
                "CPU-only here, so expect slow responses"
            )
        return "VIABLE", f"{size_gb:.1f} GB fits the {budget:.1f} GB budget"

    def verdicts(self) -> list[Verdict]:
        results: list[Verdict] = []

        # --- Unity / Android build ---
        if self.unity_ok:
            results.append(Verdict(
                "unity_android_build", "VIABLE",
                f"matching editor found at {self.unity_editor_path}",
                "this is the proven path - a real APK has already been built here",
            ))
        else:
            results.append(Verdict(
                "unity_android_build", "NOT_VIABLE",
                f"unity status is {self.raw.get('unity', {}).get('status')}",
                "install the editor version named in ProjectSettings/ProjectVersion.txt",
            ))

        # --- local LLM ---
        tier, why = self.recommend_llm_tier()
        if not self.ollama_reachable:
            results.append(Verdict(
                "local_llm", "NOT_VIABLE",
                "the Ollama HTTP API did not respond",
                "start Ollama, then re-run detect-environment.ps1",
            ))
        elif tier is None:
            results.append(Verdict("local_llm", "NOT_VIABLE", why,
                                   "close memory-heavy apps, or route these tasks to Codex/Claude"))
        else:
            status = "VIABLE" if self.has_dedicated_gpu else "LIMITED"
            gpu_note = "" if self.has_dedicated_gpu else (
                " CPU-only inference (no dedicated GPU detected), so expect slow "
                "responses - suitable for short JSON/config generation, not long reasoning"
            )
            installed = self.ollama_model_sizes
            if not installed:
                recommendation = (
                    f"pull a {tier} model, once its specific model ID is licence-checked "
                    "and APPROVED in LICENSE_REGISTRY.json"
                )
            else:
                # A pulled model that does not fit is worse than none: it looks
                # like capability. Say which ones cannot run, and downgrade the
                # verdict when nothing installed is usable.
                lines, usable = [], 0
                for name, size_gb in installed:
                    fit, fit_why = self.model_fit(size_gb)
                    if fit in ("VIABLE", "LIMITED"):
                        usable += 1
                    lines.append(f"{name}: {fit} - {fit_why}")
                if usable == 0:
                    status = "NOT_VIABLE"
                    lines.append(
                        f"nothing installed can run here; a {tier} model is what fits"
                    )
                recommendation = " | ".join(lines)
            results.append(Verdict("local_llm", status, why + gpu_note, recommendation))

        # --- local image generation ---
        if self.has_dedicated_gpu:
            results.append(Verdict(
                "local_image_generation", "LIMITED",
                "a dedicated GPU is present but its VRAM was not measured",
                "check VRAM against the model's requirement before installing anything",
            ))
        else:
            results.append(Verdict(
                "local_image_generation", "LIMITED",
                f"no dedicated GPU (found: {', '.join(self.gpu_names) or 'none'}). "
                f"Diffusion wants roughly {MIN_VRAM_GB_FOR_IMAGE_GEN:.0f} GB of VRAM "
                "and CUDA, so the standard stack will not run - but CPU and Intel "
                "iGPU paths (OpenVINO, DirectML) do work, at tens of seconds to "
                "minutes per 512px image. Slow for bulk work, fine for a handful "
                "of sprites",
                "not needed for the current art: sections 26 ranks licensed assets "
                "above generation, and the character comes from background removal "
                "of the user's own reference, which is CPU work - see the "
                "image_background_removal verdict",
            ))

        # --- background removal (segmentation, not generation) ---
        # Kept separate because conflating the two was actively misleading:
        # "no GPU" was reported as if no image work at all were possible, while
        # the thing actually needed - separating a finished character from its
        # background - is a small model that runs on the CPU in about a second.
        results.append(Verdict(
            "image_background_removal", "VIABLE",
            "u2net via rembg is a CPU segmentation model, about a second per "
            "image, and needs no GPU at all",
            "AI_GAME_COMPANY/tools/cutout-character.py - this is how the 도리 "
            "sprite was produced from the user's reference images",
        ))

        # --- image to 3D ---
        results.append(Verdict(
            "image_to_3d", "NOT_VIABLE" if not self.has_dedicated_gpu else "LIMITED",
            "single-image 3D reconstruction is GPU-bound, and section 10 already "
            "states it cannot be assumed to produce a rigged game character",
            "use Route B: a licensed pre-rigged humanoid wearing the character's "
            "appearance, which section 10 calls the higher-success path",
        ))

        # --- Codex review ---
        if self.tool_runnable("codex"):
            results.append(Verdict("codex_review", "VIABLE",
                                   "codex responded to its own version/help probe",
                                   "read config/cli-probes/codex.txt before writing the adapter"))
        elif self.tool_installed("codex"):
            results.append(Verdict(
                "codex_review", "UNKNOWN",
                "codex is installed but its help probe did not run, so no command "
                "list is verified",
                "section 41 STEP 5 forbids writing the adapter until the probe "
                "succeeds; sign in and re-run detect-environment.ps1",
            ))
        else:
            results.append(Verdict("codex_review", "NOT_VIABLE", "codex not found",
                                   "install it, then sign in (a HUMAN_GATE)"))

        # --- Blender ---
        if self.tool_runnable("blender"):
            results.append(Verdict("blender_automation", "VIABLE",
                                   "blender responded to its version probe", ""))
        elif self.tool_installed("blender"):
            results.append(Verdict("blender_automation", "UNKNOWN",
                                   "found on disk but the probe did not run", ""))
        else:
            results.append(Verdict(
                "blender_automation", "NOT_VIABLE", "blender not found",
                "only needed once there is real 3D to post-process; not on the "
                "critical path while the character is a placeholder",
            ))

        return results
