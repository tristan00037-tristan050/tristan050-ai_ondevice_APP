"""build_info: bundled stamp is read; absence degrades to unknown, never raises."""
from __future__ import annotations

import importlib
import json

import butler_pc_core.build_info as bi


def _fresh():
    importlib.reload(bi)
    bi.build_info.cache_clear()
    return bi


def test_reads_bundled_stamp(tmp_path, monkeypatch):
    mod = _fresh()
    stamp = tmp_path / "BUILD_INFO.json"
    stamp.write_text(json.dumps({
        "app": "Butler", "build_base_commit_oid": "d0cf0586d8d34ee3e7e0504deb70a0546aefe4bf",
        "build_timestamp_utc": "2026-07-15T07:47:45Z", "app_version": "0.9.0",
    }), encoding="utf-8")
    monkeypatch.setattr(mod, "_stamp_path", lambda: stamp)
    mod.build_info.cache_clear()
    info = mod.build_info()
    assert info["build_base_commit_oid"] == "d0cf0586d8d34ee3e7e0504deb70a0546aefe4bf"
    assert info["source"] == "bundled_stamp"
    assert mod.build_commit_oid() == "d0cf0586d8d34ee3e7e0504deb70a0546aefe4bf"


def test_missing_stamp_is_unknown_not_error(tmp_path, monkeypatch):
    mod = _fresh()
    monkeypatch.setattr(mod, "_stamp_path", lambda: tmp_path / "absent.json")
    monkeypatch.setattr(mod, "_git_head", lambda: "unknown")
    mod.build_info.cache_clear()
    info = mod.build_info()
    assert info["build_base_commit_oid"] == "unknown"
    assert info["source"] == "runtime_fallback"
    assert set(info) >= {"app", "build_base_commit_oid", "build_timestamp_utc", "app_version"}


def test_corrupt_stamp_falls_back(tmp_path, monkeypatch):
    mod = _fresh()
    stamp = tmp_path / "BUILD_INFO.json"
    stamp.write_text("{not json", encoding="utf-8")
    monkeypatch.setattr(mod, "_stamp_path", lambda: stamp)
    monkeypatch.setattr(mod, "_git_head", lambda: "unknown")
    mod.build_info.cache_clear()
    assert mod.build_info()["build_base_commit_oid"] == "unknown"
