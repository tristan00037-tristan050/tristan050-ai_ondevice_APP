from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

import butler_sidecar


@pytest.fixture
def stamped_build_info(monkeypatch):
    info = {
        "build_base_commit_oid": "a" * 40,
        "build_timestamp_utc": "2026-07-15T09:10:11Z",
    }
    monkeypatch.setattr(butler_sidecar, "build_info", lambda: info)
    return info


def test_health_payload_contains_build_identity(stamped_build_info):
    payload = butler_sidecar._health_payload()
    assert payload == {
        "status": "ok",
        "service": "butler-pc-core-sidecar",
        "version": "0.9.0",
        **stamped_build_info,
    }


@pytest.mark.parametrize("path", ["/health", "/api/sidecar/health"])
def test_stdlib_fallback_health_routes_share_build_identity(path, stamped_build_info):
    payload = butler_sidecar._fallback_health_payload(path)
    assert payload["build_base_commit_oid"] == stamped_build_info["build_base_commit_oid"]
    assert payload["build_timestamp_utc"] == stamped_build_info["build_timestamp_utc"]


def test_fallback_health_rejects_non_health_path():
    with pytest.raises(ValueError, match="UNSUPPORTED_FALLBACK_HEALTH_PATH"):
        butler_sidecar._fallback_health_payload("/api/model/status")


def test_stdlib_handler_serves_build_identity_without_fastapi(tmp_path):
    source = Path(butler_sidecar.__file__).resolve()
    probe = r"""
import builtins
import importlib.util
import json
import sys

real_import = builtins.__import__
def import_without_top_level_fastapi(name, globals=None, locals=None, fromlist=(), level=0):
    if globals and globals.get("__name__") == "butler_sidecar_fallback_probe" and name == "fastapi":
        raise ImportError("forced fallback")
    return real_import(name, globals, locals, fromlist, level)

builtins.__import__ = import_without_top_level_fastapi
spec = importlib.util.spec_from_file_location("butler_sidecar_fallback_probe", sys.argv[1])
module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = module
spec.loader.exec_module(module)

responses = {}
for path in ("/health", "/api/sidecar/health"):
    handler = object.__new__(module._Handler)
    handler.path = path
    captured = []
    handler._send_json = lambda code, body: captured.append((code, body))
    handler.do_GET()
    responses[path] = captured[0]
print("FALLBACK_HEALTH_JSON=" + json.dumps(responses, sort_keys=True))
"""
    completed = subprocess.run(
        [sys.executable, "-c", probe, str(source)],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        timeout=30,
        check=True,
    )
    marker = next(
        line for line in completed.stdout.splitlines() if line.startswith("FALLBACK_HEALTH_JSON=")
    )
    responses = json.loads(marker.split("=", 1)[1])
    for path in ("/health", "/api/sidecar/health"):
        status_code, payload = responses[path]
        assert status_code == 200
        assert "build_base_commit_oid" in payload
        assert "build_timestamp_utc" in payload
