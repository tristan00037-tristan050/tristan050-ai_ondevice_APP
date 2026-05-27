"""Regression guard for Codex P2 #1 (PR #755).

runtime_loader.load_runtime() previously stored str(exc) under
'error_message' on the import-failure path. The status exporter persists
that payload to evidence, so native loader failures could leak local
paths and environment details — violating the repo's meta-only /
no-raw-output rule. The real-load path (real_load_smoke.py) already
keeps only error_class plus an 'error_message_digest'; this module
must match that pattern.
"""

from unittest.mock import patch

from butler_pc_core.cards.box2 import runtime_loader as rl
from butler_pc_core.cards.box2.runtime_loader import load_runtime


SENTINEL_PATH = "/Users/PRIVATE_HOME/local_path/marker_2026_05_27"


def _force_runtime_available_then_fail(exc: Exception):
    """Force detect_runtime_packages -> available=True, then make import_module raise."""
    def _stub_detect():
        return {
            "schema_version": "box2.helper3.runtime.v3",
            "runtime_available": True,
            "runtime_packages": {"mlx_lm": True, "peft": True, "transformers": True},
            "package_versions": {"mlx_lm": "0", "peft": "0", "transformers": "0"},
            "python_version": "3.x",
            "platform": "test",
            "fail_class": None,
        }
    return patch.object(rl, "detect_runtime_packages", side_effect=_stub_detect), \
           patch.object(rl.importlib, "import_module", side_effect=exc)


def test_import_error_does_not_leak_str_exc_in_payload():
    """The sentinel local path embedded in the exception must not appear anywhere
    in the returned dict (string serialization check)."""
    exc = ImportError(f"cannot import module from {SENTINEL_PATH}")
    p1, p2 = _force_runtime_available_then_fail(exc)
    with p1, p2:
        payload = load_runtime()
    assert SENTINEL_PATH not in str(payload), (
        f"local path leaked into runtime payload: {payload}"
    )
    assert "error_message" not in payload, (
        "legacy 'error_message' key must be removed; use 'error_message_digest'"
    )


def test_import_error_keeps_error_class_and_uses_digest_key():
    """error_class is meta-only; the digest key must match the real-load path."""
    exc = RuntimeError("any error message")
    p1, p2 = _force_runtime_available_then_fail(exc)
    with p1, p2:
        payload = load_runtime()
    assert payload["error_class"] == "RuntimeError"
    assert "error_message_digest" in payload
    digest = payload["error_message_digest"]
    assert digest.startswith("sha256:")
    hex_part = digest[len("sha256:"):]
    assert len(hex_part) == 64
    assert all(c in "0123456789abcdef" for c in hex_part)


def test_import_error_redaction_matches_real_load_path():
    """The import-error path must use the same key + digest format as
    real_load_smoke.load_real_model_chain's exception branch."""
    from butler_pc_core.cards.box2 import real_load_smoke as rls
    exc = ImportError("boom")
    p1, p2 = _force_runtime_available_then_fail(exc)
    with p1, p2:
        payload = load_runtime()
    expected_digest = "sha256:" + rls._sha256_text(str(exc))
    assert payload["error_message_digest"] == expected_digest


def test_import_error_marks_fail_class():
    exc = ImportError("anything")
    p1, p2 = _force_runtime_available_then_fail(exc)
    with p1, p2:
        payload = load_runtime()
    assert payload["fail_class"] == "PARTIAL_DONE_V3_RUNTIME_IMPORT_ERROR"
    assert payload["runtime_available"] is False
