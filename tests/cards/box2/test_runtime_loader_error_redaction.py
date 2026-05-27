"""Regression guard for Codex P2 #1 (PR #755).

runtime_loader.load_runtime() previously imported native runtime modules
in-process and stored str(exc) under 'error_message' on the import-failure
path. The status exporter persists that payload to evidence, so native
loader failures could either abort pytest or leak local paths. Runtime
imports must be probed out-of-process and persist only meta status.
"""

from unittest.mock import patch

from butler_pc_core.cards.box2 import runtime_loader as rl
from butler_pc_core.cards.box2.runtime_loader import load_runtime


def _force_runtime_available_then_fail(probe_payload):
    """Force detect_runtime_packages -> available=True, then make import probe fail."""
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
           patch.object(rl, "_probe_module_import", return_value=probe_payload)


def test_import_error_does_not_leak_str_exc_in_payload():
    """Import failure payloads must not contain raw stderr/stdout/error text."""
    p1, p2 = _force_runtime_available_then_fail({
        "ok": False,
        "returncode": 134,
        "error_class": None,
    })
    with p1, p2:
        payload = load_runtime()
    assert "stderr" not in payload
    assert "stdout" not in payload
    assert "error_message" not in payload, (
        "legacy 'error_message' key must be removed; use meta status only"
    )
    assert "error_message_digest" not in payload


def test_import_error_keeps_meta_only_error_class_and_returncode():
    """error_class plus returncode are meta-only and enough for diagnosis."""
    p1, p2 = _force_runtime_available_then_fail({
        "ok": False,
        "returncode": None,
        "error_class": "TimeoutExpired",
    })
    with p1, p2:
        payload = load_runtime()
    assert payload["error_class"] == "TimeoutExpired"
    assert payload["import_returncodes"] == {"mlx_lm": None, "peft": None, "transformers": None}


def test_import_error_marks_failed_runtime_packages():
    p1, p2 = _force_runtime_available_then_fail({
        "ok": False,
        "returncode": 134,
        "error_class": None,
    })
    with p1, p2:
        payload = load_runtime()
    assert payload["runtime_packages"] == {"mlx_lm": False, "peft": False, "transformers": False}


def test_import_error_marks_fail_class():
    p1, p2 = _force_runtime_available_then_fail({
        "ok": False,
        "returncode": 134,
        "error_class": None,
    })
    with p1, p2:
        payload = load_runtime()
    assert payload["fail_class"] == "PARTIAL_DONE_V3_RUNTIME_IMPORT_ERROR"
    assert payload["runtime_available"] is False


def test_runtime_import_probe_uses_subprocess_not_inprocess_import():
    p1, p2 = _force_runtime_available_then_fail({
        "ok": True,
        "returncode": 0,
        "error_class": None,
    })
    with p1, p2, patch.object(rl.importlib, "import_module", side_effect=AssertionError("in-process import forbidden")):
        payload = load_runtime()
    assert payload["runtime_available"] is True
