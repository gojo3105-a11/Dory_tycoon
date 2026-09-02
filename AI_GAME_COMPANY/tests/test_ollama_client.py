"""Tests for the Ollama client.

Run:  python3 AI_GAME_COMPANY/tests/test_ollama_client.py

No server is needed: the transport is injected. What these actually test is
the two gates that sections 4 and 8 require, plus that an unreachable server
is reported rather than thrown at the caller as a crash.
"""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
import urllib.error
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from company.orchestrator.ollama_client import (  # noqa: E402
    ModelDoesNotFit, ModelNotApproved, ModelNotInstalled,
    NonLocalEndpointRefused, OllamaClient, OllamaUnavailable,
)


class FakeHardwareProfile:
    def __init__(self, sizes: dict[str, float], total_gb: float = 15.71,
                 free_gb: float = 10.0):
        self.ollama_model_sizes = list(sizes.items())
        self.ram_total_gb = total_gb
        self.ram_free_gb = free_gb

    def model_fit(self, size_gb: float) -> tuple[str, str]:
        if size_gb >= self.ram_total_gb:
            return "NOT_VIABLE", (
                f"{size_gb:.1f} GB of weights against {self.ram_total_gb:.1f} GB "
                "of total RAM"
            )
        if size_gb > self.ram_free_gb - 2.0:
            return "NOT_VIABLE", "exceeds the free RAM budget"
        return "LIMITED", "fits, with CPU-only inference"


class FakeTransport:
    """Answers requests from a canned map of path -> payload."""

    def __init__(self, responses: dict[str, dict], fail: bool = False):
        self.responses = responses
        self.fail = fail
        self.calls: list[str] = []

    def __call__(self, request, timeout):
        path = request.full_url.split("11434", 1)[-1] or request.full_url
        self.calls.append(path)
        if self.fail:
            raise urllib.error.URLError("connection refused")
        for key, payload in self.responses.items():
            if key in request.full_url:
                return json.dumps(payload).encode("utf-8")
        return b"{}"


class LocalOnlyTests(unittest.TestCase):
    def test_loopback_variants_are_accepted(self):
        for url in ("http://localhost:11434", "http://127.0.0.1:11434"):
            OllamaClient(url, opener=FakeTransport({}))

    def test_remote_host_is_refused(self):
        # Section 4: a config typo must not silently ship prompts off-machine.
        with self.assertRaises(NonLocalEndpointRefused):
            OllamaClient("http://some-cloud-host:11434", opener=FakeTransport({}))

    def test_remote_allowed_only_when_local_only_is_off(self):
        OllamaClient("http://some-cloud-host:11434", local_only=False,
                     opener=FakeTransport({}))


class AvailabilityTests(unittest.TestCase):
    def test_unreachable_is_reported_not_raised(self):
        client = OllamaClient(opener=FakeTransport({}, fail=True))
        reachable, detail = client.is_available()
        self.assertFalse(reachable)
        self.assertIn("failed", detail)

    def test_reachable_reports_timing(self):
        client = OllamaClient(opener=FakeTransport({"/api/tags": {"models": []}}))
        reachable, detail = client.is_available()
        self.assertTrue(reachable)
        self.assertIn("ms", detail)

    def test_list_models_parses_details(self):
        client = OllamaClient(opener=FakeTransport({"/api/tags": {"models": [{
            "name": "qwen2.5:3b", "size": 2 * 1024 ** 3,
            "details": {"parameter_size": "3B", "quantization_level": "Q4_K_M"},
        }]}}))
        models = client.list_models()
        self.assertEqual(models[0].name, "qwen2.5:3b")
        self.assertEqual(models[0].size_gb, 2.0)
        self.assertEqual(models[0].quantization, "Q4_K_M")

    def test_no_models_says_so_plainly(self):
        client = OllamaClient(opener=FakeTransport({"/api/tags": {"models": []}}))
        summary = client.status_summary()
        self.assertIn("NO models installed", summary)
        self.assertIn("APPROVED", summary)  # says what unblocks it

    def test_generate_raises_when_server_is_down(self):
        client = OllamaClient(registry_path=_registry_with(["qwen2.5:3b"]),
                              opener=FakeTransport({}, fail=True))
        with self.assertRaises(OllamaUnavailable):
            client.generate("qwen2.5:3b", "hello")


_TMPDIRS: list[tempfile.TemporaryDirectory] = []


def _registry_with(model_ids: list[str], status: str = "APPROVED") -> Path:
    tmp = tempfile.TemporaryDirectory()
    _TMPDIRS.append(tmp)  # kept alive for the test session
    path = Path(tmp.name) / "LICENSE_REGISTRY.json"
    path.write_text(json.dumps({
        "entries": [{
            "id": model_ids[0], "type": "ai_model", "status": status,
            "model_ids": model_ids,
        }]
    }), encoding="utf-8")
    return path


class ApprovedModelGateTests(unittest.TestCase):
    def setUp(self):
        self.transport = FakeTransport({
            "/api/tags": {"models": [{"name": "qwen2.5:3b", "size": 0}]},
            "/api/generate": {"response": "generated text"},
        })

    def test_no_approved_models_blocks_everything(self):
        client = OllamaClient(registry_path=None, opener=self.transport)
        with self.assertRaises(ModelNotApproved) as ctx:
            client.generate("qwen2.5:3b", "hi")
        # The message must say WHY, and reject the family-name shortcut.
        self.assertIn("not sufficient", str(ctx.exception))

    def test_unapproved_model_blocked_even_when_others_are_approved(self):
        client = OllamaClient(registry_path=_registry_with(["qwen2.5:3b"]),
                              opener=self.transport)
        with self.assertRaises(ModelNotApproved) as ctx:
            client.generate("deepseek-r1:7b", "hi")
        self.assertIn("qwen2.5:3b", str(ctx.exception))

    def test_no_request_is_sent_for_an_unapproved_model(self):
        # The gate must run BEFORE the network call, not after.
        client = OllamaClient(registry_path=None, opener=self.transport)
        with self.assertRaises(ModelNotApproved):
            client.generate("qwen2.5:3b", "hi")
        self.assertEqual(self.transport.calls, [])

    def test_approved_model_generates(self):
        client = OllamaClient(registry_path=_registry_with(["qwen2.5:3b"]),
                              opener=self.transport)
        self.assertEqual(client.generate("qwen2.5:3b", "hi"), "generated text")

    def test_registry_status_other_than_approved_is_not_enough(self):
        client = OllamaClient(registry_path=_registry_with(["qwen2.5:3b"], status="UNKNOWN"),
                              opener=self.transport)
        with self.assertRaises(ModelNotApproved):
            client.generate("qwen2.5:3b", "hi")

    def test_non_model_entries_do_not_grant_approval(self):
        # An APPROVED art pack must not accidentally approve an LLM.
        tmp = tempfile.TemporaryDirectory()
        _TMPDIRS.append(tmp)
        path = Path(tmp.name) / "LICENSE_REGISTRY.json"
        path.write_text(json.dumps({"entries": [{
            "id": "qwen2.5:3b", "type": "2d_art_pack", "status": "APPROVED",
        }]}), encoding="utf-8")

        client = OllamaClient(registry_path=path, opener=self.transport)
        with self.assertRaises(ModelNotApproved):
            client.generate("qwen2.5:3b", "hi")

    def test_summary_marks_installed_but_unapproved_models(self):
        client = OllamaClient(registry_path=None, opener=self.transport)
        self.assertIn("NOT APPROVED", client.status_summary())


class ActiveModelTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.state_path = Path(self.tmp.name) / "company_state.json"
        self.transport = FakeTransport({"/api/tags": {"models": [
            {"name": "qwen2.5:3b", "size": 2 * 1024 ** 3},
            {"name": "unapproved:3b", "size": 2 * 1024 ** 3},
            {"name": "gemma4:26b", "size": int(17.33 * 1024 ** 3)},
        ]}})
        self.profile = FakeHardwareProfile({
            "qwen2.5:3b": 2.0,
            "unapproved:3b": 2.0,
            "gemma4:26b": 17.33,
        })
        self.registry = _registry_with(["qwen2.5:3b", "gemma4:26b", "missing:3b"])

    def tearDown(self):
        self.tmp.cleanup()

    def client(self) -> OllamaClient:
        return OllamaClient(registry_path=self.registry, opener=self.transport,
                            state_path=self.state_path)

    def test_use_accepts_approved_installed_model_that_fits(self):
        self.client().use_model("qwen2.5:3b", self.profile)
        self.assertEqual(self.client().active_model(), "qwen2.5:3b")

    def test_use_refuses_unapproved_model(self):
        with self.assertRaisesRegex(ModelNotApproved, "licence check failed"):
            self.client().use_model("unapproved:3b", self.profile)

    def test_use_checks_licence_before_contacting_ollama(self):
        client = self.client()
        with self.assertRaises(ModelNotApproved):
            client.use_model("unapproved:3b", self.profile)
        self.assertEqual(self.transport.calls, [])

    def test_use_refuses_oversized_model_with_size_and_machine_total(self):
        with self.assertRaises(ModelDoesNotFit) as ctx:
            self.client().use_model("gemma4:26b", self.profile)
        self.assertIn("17.33 GB", str(ctx.exception))
        self.assertIn("15.71 GB", str(ctx.exception))

    def test_use_refuses_model_that_is_not_installed(self):
        with self.assertRaisesRegex(ModelNotInstalled, "installation check failed"):
            self.client().use_model("missing:3b", self.profile)

    def test_persisted_choice_survives_reload_and_preserves_state(self):
        self.state_path.write_text(json.dumps({"ollama_status": "READY"}),
                                   encoding="utf-8")
        self.client().use_model("qwen2.5:3b", self.profile)
        reloaded = self.client()
        self.assertEqual(reloaded.active_model(), "qwen2.5:3b")
        state = json.loads(self.state_path.read_text(encoding="utf-8"))
        self.assertEqual(state["ollama_status"], "READY")


if __name__ == "__main__":
    unittest.main(verbosity=2)
