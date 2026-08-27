"""AI routing (master prompt section 16).

Cheap work goes to the local model, high-risk work goes to Claude with an
independent Codex review, and every route degrades to whatever is actually
available. When Claude and Codex disagree, the tie-break is not a third
opinion - it is the real compile/test/build result (section 16).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .claude_runner import ClaudeRunner
from .codex_runner import CodexRunner
from .ollama_client import OllamaClient
from .policy import Policy

LOW, MEDIUM, HIGH_RISK = "LOW", "MEDIUM", "HIGH_RISK"

LOCAL_PLANNER = "local_planner"
LOCAL_REASONER = "local_reasoner"
CLAUDE = "claude"
CODEX = "codex"
HUMAN = "human"

# Task kind -> (risk tier, primary chain, reviewer)
ROUTES: dict[str, dict[str, Any]] = {
    "json_config":        {"risk": LOW,       "chain": [LOCAL_PLANNER, CLAUDE], "reviewer": None},
    "game_data":          {"risk": LOW,       "chain": [LOCAL_PLANNER, CLAUDE], "reviewer": None},
    "checklist":          {"risk": LOW,       "chain": [LOCAL_PLANNER, CLAUDE], "reviewer": None},
    "test_case":          {"risk": LOW,       "chain": [LOCAL_PLANNER, CLAUDE], "reviewer": None},
    "doc_draft":          {"risk": LOW,       "chain": [LOCAL_PLANNER, CLAUDE], "reviewer": None},
    "idea_expansion":     {"risk": LOW,       "chain": [LOCAL_PLANNER, CLAUDE], "reviewer": None},
    "build_log_triage":   {"risk": MEDIUM,    "chain": [LOCAL_REASONER, CLAUDE], "reviewer": CLAUDE},
    "stack_trace":        {"risk": MEDIUM,    "chain": [LOCAL_REASONER, CLAUDE], "reviewer": CLAUDE},
    "design_alternative": {"risk": MEDIUM,    "chain": [LOCAL_REASONER, CLAUDE], "reviewer": CLAUDE},
    "perf_estimate":      {"risk": MEDIUM,    "chain": [LOCAL_REASONER, CLAUDE], "reviewer": CLAUDE},
    "core_system":        {"risk": HIGH_RISK, "chain": [CLAUDE],  "reviewer": CODEX},
    "save_system":        {"risk": HIGH_RISK, "chain": [CLAUDE],  "reviewer": CODEX},
    "android_build_fix":  {"risk": HIGH_RISK, "chain": [CLAUDE],  "reviewer": CODEX},
    "code_review":        {"risk": HIGH_RISK, "chain": [CODEX, LOCAL_REASONER, CLAUDE], "reviewer": CLAUDE},
    "architecture":       {"risk": HIGH_RISK, "chain": [CLAUDE],  "reviewer": CODEX},
    "release_approval":   {"risk": HIGH_RISK, "chain": [HUMAN],   "reviewer": HUMAN},
}


@dataclass
class RoutingPlan:
    task_kind: str
    risk: str
    selected: str | None
    chain: list[str] = field(default_factory=list)
    unavailable: list[dict[str, str]] = field(default_factory=list)
    reviewer: str | None = None
    reviewer_available: bool = False
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_kind": self.task_kind, "risk": self.risk,
            "selected": self.selected, "chain": self.chain,
            "unavailable": self.unavailable, "reviewer": self.reviewer,
            "reviewer_available": self.reviewer_available, "notes": self.notes,
        }


class AgentRouter:
    def __init__(self, policy: Policy | None = None,
                 availability: dict[str, Any] | None = None):
        self.policy = policy or Policy.load()
        self._availability = availability

    # ---- availability ------------------------------------------------
    def availability(self, *, refresh: bool = False) -> dict[str, Any]:
        if self._availability is not None and not refresh:
            return self._availability
        ollama = OllamaClient(self.policy).health()
        codex = CodexRunner(self.policy).capabilities()
        claude = ClaudeRunner(self.policy).capabilities()
        local_ok = ollama["status"] == "OK"
        self._availability = {
            LOCAL_PLANNER: {"available": local_ok,
                            "reason": ollama.get("error") or ollama["status"],
                            "models": ollama.get("models", [])},
            LOCAL_REASONER: {"available": local_ok,
                             "reason": ollama.get("error") or ollama["status"],
                             "models": ollama.get("models", [])},
            CODEX: {"available": codex.get("status") == "OK" and codex.get("exec", False),
                    "reason": codex.get("status")},
            CLAUDE: {"available": claude.get("installed") and claude.get("headless"),
                     "reason": claude.get("status"),
                     "note": claude.get("note")},
            HUMAN: {"available": True, "reason": "HUMAN_GATE"},
        }
        return self._availability

    # ---- routing -----------------------------------------------------
    def route(self, task_kind: str) -> RoutingPlan:
        route = ROUTES.get(task_kind)
        if route is None:
            route = {"risk": HIGH_RISK, "chain": [CLAUDE], "reviewer": CODEX}
            notes = [f"unknown task kind '{task_kind}': treated as HIGH_RISK"]
        else:
            notes = []
        avail = self.availability()
        plan = RoutingPlan(task_kind=task_kind, risk=route["risk"],
                           selected=None, chain=list(route["chain"]),
                           reviewer=route.get("reviewer"), notes=notes)
        for agent in plan.chain:
            if avail.get(agent, {}).get("available"):
                plan.selected = agent
                break
            plan.unavailable.append({"agent": agent,
                                     "reason": str(avail.get(agent, {}).get("reason"))})
        if plan.selected is None:
            plan.selected = HUMAN
            plan.notes.append("no automated agent available; escalating to HUMAN_GATE")
        if plan.reviewer:
            plan.reviewer_available = bool(avail.get(plan.reviewer, {}).get("available"))
            if not plan.reviewer_available and plan.reviewer == CODEX:
                plan.notes.append("codex unavailable: review falls back to local "
                                  "reasoner then Claude (section 3)")
        if plan.risk == HIGH_RISK and plan.selected in (LOCAL_PLANNER, LOCAL_REASONER):
            plan.notes.append("HIGH_RISK task on a local model: a Claude review is "
                              "mandatory before PASS")
        return plan

    @staticmethod
    def resolve_disagreement(claude_verdict: str, codex_verdict: str,
                             build_result: dict[str, Any] | None) -> dict[str, Any]:
        """Real build/test output outranks both opinions (section 16)."""
        if claude_verdict == codex_verdict:
            return {"resolution": claude_verdict, "decided_by": "consensus",
                    "note": "both reviewers agree"}
        if build_result is not None:
            status = build_result.get("status") or build_result.get("verdict")
            passed = bool(build_result.get("ok")) or status in ("OK", "SUCCESS", "PASS")
            return {
                "resolution": "PASS" if passed else "FAIL",
                "decided_by": "actual_build_or_test_result",
                "note": f"reviewers disagreed (claude={claude_verdict}, "
                        f"codex={codex_verdict}); machine result wins",
                "evidence": build_result,
            }
        return {"resolution": "NEEDS_HUMAN_REVIEW", "decided_by": "no_machine_evidence",
                "note": "reviewers disagreed and no compile/test/build result exists yet"}
