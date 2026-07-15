"""Phase 3 Stage 6: scripts/verify-credentials.py + scripts/lib/credential_validators tests.

Coverage targets:
- Unit: ValidationResult / BatchResult / load_dotenv / hint error code mapping
- Integration (subprocess): run verify-credentials.py in a **clean environment**
    → All three keys unconfigured → must output valid JSON with error == "E000" and non-zero exit code
- Unit (mock all three services): via patch of ``health.check_*`` verify
    validate_tencent / validate_trtc / validate_llm / validate_all chain
    returned ValidationResult fields match ``{ok, type, error, message, latency_ms}``

Red lines (aligned with SKILL.md §12 Tool Whitelist):
- Verification script **does not** accept keys as CLI arguments → tests only use .env and patch
- Output JSON must not contain credential plaintext (latency_ms / error code only)
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))


def _run_cli(env_extra=None, args=None):
    """Fork a verify-credentials.py subprocess in an isolated environment.

    Explicitly empties all three Key env variables to prevent .env file fallback overrides
    (load_dotenv uses setdefault; empty strings in env prevent real values from .env injection).
    """
    env = {
        "PATH": os.environ.get("PATH", ""),
        "HOME": os.environ.get("HOME", ""),
        "PYTHONPATH": str(_ROOT),
        # Force clear all candidate env variables to ensure ``configured`` is False
        "TENCENT_CLOUD_SECRET_ID": "",
        "TENCENT_CLOUD_SECRET_KEY": "",
        "TRTC_SDK_APP_ID": "",
        "TRTC_SDK_SECRET_KEY": "",
        "LLM_API_KEY": "",
        "LLM_API_URL": "",
        "LLM_MODEL": "",
    }
    if env_extra:
        env.update(env_extra)
    cmd = [sys.executable, str(_ROOT / "scripts" / "verify-credentials.py")]
    if args:
        cmd.extend(args)
    proc = subprocess.run(
        cmd,
        cwd=str(_ROOT),
        capture_output=True,
        text=True,
        timeout=20,
        env=env,
    )
    return proc


class CredentialValidatorsUnitTests(unittest.TestCase):
    """Pure unit tests for the credential_validators module (no network calls)."""

    def test_validation_result_to_dict_keys(self):
        from scripts.lib.credential_validators import ValidationResult
        r = ValidationResult(ok=True, type="tencent", message="ok", latency_ms=42)
        d = r.to_dict()
        self.assertSetEqual(
            set(d.keys()), {"ok", "type", "error", "message", "latency_ms"}
        )
        self.assertTrue(d["ok"])
        self.assertEqual(d["type"], "tencent")

    def test_batch_result_aggregates(self):
        from scripts.lib.credential_validators import BatchResult, ValidationResult
        b = BatchResult(
            ok=False,
            items=[
                ValidationResult(ok=True, type="tencent"),
                ValidationResult(ok=False, type="trtc", error="E002", message="fail"),
                ValidationResult(ok=True, type="llm"),
            ],
        )
        d = b.to_dict()
        self.assertEqual(d["type"], "all")
        self.assertFalse(d["ok"])
        self.assertEqual(len(d["items"]), 3)
        self.assertEqual(d["items"][1]["error"], "E002")

    def test_hint_returns_known_codes(self):
        from scripts.lib.credential_validators import hint
        self.assertIn("腾讯云", hint("E001"))
        self.assertIn("TRTC", hint("E002"))
        self.assertIn("LLM", hint("E003"))
        # Unknown error code → empty string
        self.assertEqual(hint("E999"), "")

    def test_load_dotenv_reads_kv(self):
        from scripts.lib.credential_validators import load_dotenv
        with tempfile.TemporaryDirectory() as td:
            envf = Path(td) / ".env"
            envf.write_text(
                "FAKE_KEY_FOR_TEST=hello\n# comment\nFAKE_QUOTED=\"world\"\n",
                encoding="utf-8",
            )
            try:
                # Clear same-name process-level vars to ensure reading from file
                os.environ.pop("FAKE_KEY_FOR_TEST", None)
                os.environ.pop("FAKE_QUOTED", None)
                seen = load_dotenv(envf)
                self.assertEqual(seen.get("FAKE_KEY_FOR_TEST"), "hello")
                self.assertEqual(seen.get("FAKE_QUOTED"), "world")
                self.assertEqual(os.environ.get("FAKE_KEY_FOR_TEST"), "hello")
            finally:
                os.environ.pop("FAKE_KEY_FOR_TEST", None)
                os.environ.pop("FAKE_QUOTED", None)


class VerifyCredentialsCliEmptyEnvTests(unittest.TestCase):
    """Subprocess: verify-credentials.py behavior in a clean environment (no .env, no keys)."""

    def setUp(self):
        # Use a clean tmp directory as cwd stand-in: point --env-file to a non-existent path
        # while eliminating the chance of hitting the repo root .env / capabilities/conversation-core/.env
        self.tmp = tempfile.TemporaryDirectory()
        self.empty_env = Path(self.tmp.name) / "no.env"
        self.empty_env.write_text("# empty\n", encoding="utf-8")

    def tearDown(self):
        self.tmp.cleanup()

    def _run(self, *extra_args):
        return _run_cli(args=["--env-file", str(self.empty_env), *extra_args])

    def test_tencent_empty_returns_e000(self):
        proc = self._run("--type", "tencent")
        self.assertNotEqual(proc.returncode, 0, proc.stderr)
        out = json.loads(proc.stdout.strip())
        self.assertFalse(out["ok"])
        self.assertEqual(out["type"], "tencent")
        self.assertEqual(out["error"], "E000")
        self.assertSetEqual(
            set(out.keys()), {"ok", "type", "error", "message", "latency_ms"}
        )
        # Output must not contain real keys (empty_env also ensures this)
        self.assertNotIn("AKID", proc.stdout)
        self.assertNotIn("AKID", proc.stderr)

    def test_trtc_empty_returns_e000(self):
        proc = self._run("--type", "trtc")
        out = json.loads(proc.stdout.strip())
        self.assertFalse(out["ok"])
        self.assertEqual(out["type"], "trtc")
        self.assertEqual(out["error"], "E000")

    def test_llm_empty_returns_e000(self):
        proc = self._run("--type", "llm")
        out = json.loads(proc.stdout.strip())
        self.assertFalse(out["ok"])
        self.assertEqual(out["type"], "llm")
        self.assertEqual(out["error"], "E000")

    def test_all_empty_returns_three_items(self):
        proc = self._run("--type", "all")
        self.assertNotEqual(proc.returncode, 0)
        out = json.loads(proc.stdout.strip())
        self.assertEqual(out["type"], "all")
        self.assertFalse(out["ok"])
        types = {item["type"] for item in out["items"]}
        self.assertSetEqual(types, {"tencent", "trtc", "llm"})


class VerifyCredentialsMockedNetworkTests(unittest.TestCase):
    """Patch health.check_* to simulate success / failure responses from all three services."""

    def setUp(self):
        # Inject fake keys at process level (only to make ``configured`` return True)
        self._keys = {
            "TENCENT_CLOUD_SECRET_ID": "AKID_TEST_FAKE_FAKE_FAKE_FAKE_FAKE_X",
            "TENCENT_CLOUD_SECRET_KEY": "FakeKeyFakeKeyFakeKeyFakeKeyFakeKey",
            "TRTC_SDK_APP_ID": "1400000001",
            "TRTC_SDK_SECRET_KEY": "FakeTRTCSdkSecretKeyFakeTRTCSdkSecretKey",
            "LLM_API_KEY": "sk-fake-test-key",
            "LLM_API_URL": "https://api.openai.example/v1/chat/completions",
            "LLM_MODEL": "gpt-test",
            "LLM_TYPE": "openai",
        }
        self._saved = {k: os.environ.get(k) for k in self._keys}
        for k, v in self._keys.items():
            os.environ[k] = v

    def tearDown(self):
        for k, prev in self._saved.items():
            if prev is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = prev

    def _import_health(self):
        """Explicitly import conversation-core's health module for patching.

        Clean all cached ``src.*`` modules (side effect from test_handoff_ports / test_kb_ports),
        and push conversation-core to the top of sys.path so ``src`` resolves back to this capability.
        """
        core_dir = _ROOT / "capabilities" / "conversation-core"
        # First clean up src.* modules injected by previous tests
        for name in [k for k in list(sys.modules) if k == "src" or k.startswith("src.")]:
            del sys.modules[name]
        # Also remove other capabilities paths from sys.path to avoid ambiguity
        sys.path[:] = [p for p in sys.path if "/capabilities/" not in p]
        sys.path.insert(0, str(core_dir))
        import importlib  # noqa: WPS433
        return importlib.import_module("src.health")

    def test_tencent_ok(self):
        h = self._import_health()
        from scripts.lib.credential_validators import validate_tencent
        with patch.object(h, "check_tencent_cloud") as m:
            m.return_value = h.CheckResult(ok=True, latency_ms=120, detail="sts ok")
            r = validate_tencent()
        self.assertTrue(r.ok)
        self.assertEqual(r.type, "tencent")
        self.assertEqual(r.error, "")
        self.assertEqual(r.latency_ms, 120)

    def test_tencent_failure_maps_to_e001(self):
        h = self._import_health()
        from scripts.lib.credential_validators import validate_tencent
        with patch.object(h, "check_tencent_cloud") as m:
            m.return_value = h.CheckResult(
                ok=False, latency_ms=33, error_code="E001", detail="AuthFailure"
            )
            r = validate_tencent()
        self.assertFalse(r.ok)
        self.assertEqual(r.error, "E001")
        # Must not echo key plaintext
        self.assertNotIn("FakeKey", r.message)

    def test_trtc_ok_local_only(self):
        h = self._import_health()
        from scripts.lib.credential_validators import validate_trtc
        with patch.object(h, "check_trtc") as m:
            m.return_value = h.CheckResult(ok=True, latency_ms=12, detail="local-only")
            r = validate_trtc(deep=False)
        self.assertTrue(r.ok)
        self.assertEqual(r.type, "trtc")

    def test_llm_failure_maps_to_e003(self):
        h = self._import_health()
        from scripts.lib.credential_validators import validate_llm
        with patch.object(h, "check_llm") as m:
            m.return_value = h.CheckResult(
                ok=False, latency_ms=55, error_code="E003", detail="401 Unauthorized"
            )
            r = validate_llm()
        self.assertFalse(r.ok)
        self.assertEqual(r.error, "E003")
        self.assertEqual(r.type, "llm")
        # Output message must not contain raw sk-* credentials
        self.assertNotIn("sk-fake", r.message)

    def test_validate_all_aggregates(self):
        h = self._import_health()
        from scripts.lib.credential_validators import validate_all
        with patch.object(h, "check_tencent_cloud") as a, \
             patch.object(h, "check_trtc") as b, \
             patch.object(h, "check_llm") as c:
            a.return_value = h.CheckResult(ok=True, latency_ms=100)
            b.return_value = h.CheckResult(ok=True, latency_ms=80, detail="ok")
            c.return_value = h.CheckResult(ok=False, latency_ms=20, error_code="E003", detail="boom")
            batch = validate_all()
        self.assertFalse(batch.ok)
        items = batch.to_dict()["items"]
        self.assertEqual(len(items), 3)
        # Order is fixed: tencent → trtc → llm
        self.assertEqual([i["type"] for i in items], ["tencent", "trtc", "llm"])


if __name__ == "__main__":
    unittest.main()
