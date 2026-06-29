"""수정3 검증 — usage_log device-local 기본 저장 경로(0600, fallback, disable).

필수 테스트:
  · BUTLER_USAGE_LOG_PATH 미설정에도 device-local 기본 JSONL 저장.
  · DISABLE_PERSIST=1 이면 파일 사이드이펙트 0.
  · 새 파일 0600 권한 + JSONL 에 schema-valid digest-only record 만.
"""
from __future__ import annotations

import json
import stat

from butler_pc_core.sidecar.middleware import usage_accumulator as ua
from butler_pc_core.sidecar.middleware.usage_accumulator import (
    ENV_USAGE_LOG_DISABLE_PERSIST,
    ENV_USAGE_LOG_PATH,
    ENV_USER_DATA_DIR,
    UsageLogStore,
    build_accounting_usage_log,
    resolve_usage_log_path,
)


def _clear_env(monkeypatch):
    for var in (ENV_USAGE_LOG_PATH, ENV_USAGE_LOG_DISABLE_PERSIST, ENV_USER_DATA_DIR):
        monkeypatch.delenv(var, raising=False)


def _valid_record():
    return build_accounting_usage_log(
        result_id="rid-1", summary={"total_rows": 2}, latency_ms=10.0
    )


def test_explicit_path_takes_priority(tmp_path, monkeypatch):
    _clear_env(monkeypatch)
    target = tmp_path / "explicit" / "usage.jsonl"
    monkeypatch.setenv(ENV_USAGE_LOG_PATH, str(target))
    assert resolve_usage_log_path() == target


def test_disable_persist_yields_none_and_no_file(tmp_path, monkeypatch):
    _clear_env(monkeypatch)
    monkeypatch.setenv(ENV_USAGE_LOG_DISABLE_PERSIST, "1")
    assert resolve_usage_log_path() is None
    store = UsageLogStore()
    store.append(_valid_record())
    # in-memory 에는 남지만 파일 사이드이펙트는 0.
    assert len(store.records) == 1


def test_user_data_dir_default_path(tmp_path, monkeypatch):
    _clear_env(monkeypatch)
    monkeypatch.setenv(ENV_USER_DATA_DIR, str(tmp_path))
    expected = tmp_path / "connect_loop" / "usage_log.jsonl"
    assert resolve_usage_log_path() == expected


def test_append_writes_default_path_jsonl_0600(tmp_path, monkeypatch):
    """BUTLER_USAGE_LOG_PATH 미설정(USER_DATA_DIR 기본)에도 JSONL 저장 + 새 파일 0600."""
    _clear_env(monkeypatch)
    monkeypatch.setenv(ENV_USER_DATA_DIR, str(tmp_path))
    target = tmp_path / "connect_loop" / "usage_log.jsonl"

    store = UsageLogStore()
    record = _valid_record()
    store.append(record)

    assert target.exists(), "device-local 기본 경로에 JSONL 이 생성되어야 한다"
    # 새 파일 권한 0600(소유자 전용).
    mode = stat.S_IMODE(target.stat().st_mode)
    assert mode == 0o600, f"새 파일 권한이 0600 이어야 한다 (실제: {oct(mode)})"
    # JSONL 1줄 = schema-valid digest-only record. 원문/파일명/temp path 없음.
    lines = target.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1
    stored = json.loads(lines[0])
    assert stored["retention_class"] == "audit_digest_only"
    assert stored["raw_text_logged"] is False
    assert stored["external_send_zero"] is True


def test_append_failure_does_not_raise(monkeypatch):
    """저장 경로가 잘못돼도(예: 디렉터리 생성 불가) 응답을 깨뜨리지 않는다."""
    _clear_env(monkeypatch)
    # 파일을 만들 수 없는 경로(기존 파일을 부모 디렉터리로 사용)를 강제.
    monkeypatch.setattr(ua, "resolve_usage_log_path", lambda: ua.Path("/dev/null/cannot/usage.jsonl"))
    store = UsageLogStore()
    store.append(_valid_record())  # 예외 없이 통과해야 한다
    assert len(store.records) == 1
