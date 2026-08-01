"""
Capability token 인증 계약 테스트.

본 파일은 다음 본질을 검증한다:
1. 결함 #1 회귀 방지 — 토큰 파일 unreadable 시 CapabilityTokenError 본질
   (generic OSError escape 0, fail-closed deterministic 분류 유지)
2. 결함 #2 회귀 방지 — 실제 FastAPI 라우트 본질 검증:
   - public paths: 토큰 없이도 401 아님 (TestClient 실호출)
   - protected paths: 토큰 없이 401 (PR #750 본질에 통합 0 → skipif)
3. 기존 CapabilityTokenManager 단위 본질 (verify_authorization_header 4건) 보존
"""
from __future__ import annotations

import errno
import stat
from pathlib import Path

import pytest

from butler_pc_core.auth.capability_token import (
    CapabilityTokenError,
    CapabilityTokenManager,
    auth_error_payload,
)
from butler_pc_core.fail_class import FailClass


# ------------------------------------------------------------------------------
# View-4 식별 본질: PUBLIC / PROTECTED 라우트
#
# 운영상태·측정결과처럼 신뢰 경계 내부인 GET은 capability token이 필요하다.
# 공개 health/model status와 혼동하지 않도록 실제 FastAPI 경로를 직접 호출한다.
# ------------------------------------------------------------------------------
PUBLIC_PATHS: list[tuple[str, str]] = [
    ("GET", "/health"),
    ("GET", "/api/sidecar/health"),
    ("GET", "/api/model/status"),
]

PROTECTED_GET_PATHS: list[tuple[str, str]] = [
    ("GET", "/api/egress/report"),
    ("GET", "/v1/home/bootstrap-status"),
    ("GET", "/v1/home/snapshot"),
]


# ------------------------------------------------------------------------------
# 결함 #1 회귀 방지 — token file unreadable → CapabilityTokenError (fail-closed)
# ------------------------------------------------------------------------------

def test_token_file_unreadable_raises_capability_token_error(tmp_path, monkeypatch):
    """
    토큰 파일이 존재하나 OSError 발생 시 CapabilityTokenError 본질.
    generic Exception escape 0 → 500 추락 0 → fail-closed 분류 유지.
    """
    token_file = tmp_path / "sidecar_token"
    token_file.write_text("dummy", encoding="utf-8")

    def _raise_oserror(*args, **kwargs):
        raise OSError(errno.EACCES, "Permission denied (simulated drift)")

    monkeypatch.setattr(Path, "read_text", _raise_oserror)

    manager = CapabilityTokenManager(token_file)
    with pytest.raises(CapabilityTokenError) as exc_info:
        _ = manager.token  # @property — 읽기 트리거
    assert exc_info.value.fail_class == FailClass.CAPABILITY_TOKEN_INVALID
    assert "unreadable" in exc_info.value.message
    # 인과 체인 보존 본질
    assert isinstance(exc_info.value.__cause__, OSError)


def test_token_file_unreadable_payload_classifies_invalid(tmp_path, monkeypatch):
    """결함 #1 회귀 — auth_error_payload 본질도 deterministic classification."""
    token_file = tmp_path / "sidecar_token"
    token_file.write_text("dummy", encoding="utf-8")
    monkeypatch.setattr(
        Path,
        "read_text",
        lambda *a, **k: (_ for _ in ()).throw(OSError(errno.EIO, "I/O")),
    )
    manager = CapabilityTokenManager(token_file)
    with pytest.raises(CapabilityTokenError) as exc_info:
        _ = manager.token
    payload = auth_error_payload(exc_info.value)
    assert payload["fail_class"] == "CAPABILITY_TOKEN_INVALID"


def test_token_file_missing_does_not_raise(tmp_path):
    """파일 0 본질 (정상 케이스) — raise 0."""
    manager = CapabilityTokenManager(tmp_path / "absent")
    assert manager.token is None  # raise 0


# ------------------------------------------------------------------------------
# 결함 #2 회귀 방지 — 실제 FastAPI 라우트 본질 (TestClient 실호출)
# ------------------------------------------------------------------------------

@pytest.fixture(scope="module")
def client():
    """butler_sidecar app 본질 TestClient."""
    fastapi_testclient = pytest.importorskip("fastapi.testclient")
    try:
        from butler_sidecar import app  # type: ignore[attr-defined]
    except ImportError as exc:
        pytest.skip(f"butler_sidecar import 본질 0: {exc}")
    if app is None:
        pytest.skip("butler_sidecar.app 본질 None (_FASTAPI_AVAILABLE 0)")
    return fastapi_testclient.TestClient(app)


@pytest.mark.parametrize("method,path", PUBLIC_PATHS, ids=lambda x: f"{x[0]}_{x[1]}" if isinstance(x, tuple) else str(x))
def test_public_paths_no_token_not_401(client, method, path):
    """
    public path는 토큰 없이 호출 시 401이 아니어야 한다.
    (200/204/307/404/500 등 본질 허용 — 401만 차단)
    """
    resp = client.request(method, path)
    assert resp.status_code != 401, (
        f"public path {method} {path} 본질이 토큰 요구: status={resp.status_code}"
    )


@pytest.mark.parametrize(
    "method,path",
    PROTECTED_GET_PATHS,
    ids=lambda x: f"{x[0]}_{x[1]}" if isinstance(x, tuple) else str(x),
)
@pytest.mark.skipif(
    not PROTECTED_GET_PATHS,
    reason="보호 GET 경로 계약이 아직 정의되지 않음",
)
def test_protected_paths_no_token_returns_401(client, method, path):
    """protected path는 토큰 없이 호출 시 반드시 401."""
    resp = client.request(method, path)
    assert resp.status_code == 401, (
        f"protected path {method} {path} 본질이 401 아님: status={resp.status_code}"
    )


# ------------------------------------------------------------------------------
# 기존 본질 보존 — CapabilityTokenManager 단위 (verify_authorization_header)
# ------------------------------------------------------------------------------

def test_post_no_token_401_contract(tmp_path):
    """기존 본질 보존 — Authorization header 0 시 MISSING."""
    manager = CapabilityTokenManager(tmp_path / "sidecar_token")
    manager.generate()
    with pytest.raises(CapabilityTokenError) as exc_info:
        manager.verify_authorization_header(None)
    assert exc_info.value.fail_class == FailClass.CAPABILITY_TOKEN_MISSING
    assert auth_error_payload(exc_info.value)["fail_class"] == "CAPABILITY_TOKEN_MISSING"


def test_post_invalid_token_403_contract(tmp_path):
    """기존 본질 보존 — 잘못된 토큰 시 INVALID."""
    manager = CapabilityTokenManager(tmp_path / "sidecar_token")
    manager.generate()
    with pytest.raises(CapabilityTokenError) as exc_info:
        manager.verify_authorization_header("Bearer wrong-token")
    assert exc_info.value.fail_class == FailClass.CAPABILITY_TOKEN_INVALID
    assert auth_error_payload(exc_info.value)["fail_class"] == "CAPABILITY_TOKEN_INVALID"


def test_post_valid_token_200_contract(tmp_path):
    """기존 본질 보존 — 올바른 토큰 시 raise 0."""
    manager = CapabilityTokenManager(tmp_path / "sidecar_token")
    token = manager.generate()
    session = manager.verify_authorization_header(f"Bearer {token}")
    assert session.actor_id == "local-user"
    assert session.role == "user"
    assert len(session.session_digest) == 64


def test_token_file_chmod_600(tmp_path):
    """기존 본질 보존 — chmod 0600 + clear() 본질."""
    token_path = tmp_path / "sidecar_token"
    manager = CapabilityTokenManager(token_path)
    manager.generate()
    mode = stat.S_IMODE(token_path.stat().st_mode)
    assert mode == 0o600
    manager.clear()
    assert not token_path.exists()
