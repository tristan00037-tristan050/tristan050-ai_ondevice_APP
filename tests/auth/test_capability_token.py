from __future__ import annotations

import stat

import pytest

from butler_pc_core.auth.capability_token import (
    CapabilityTokenError,
    CapabilityTokenManager,
    auth_error_payload,
)
from butler_pc_core.fail_class import FailClass


def test_health_no_token_allowed_contract():
    public_paths = {
        ("GET", "/health"),
        ("GET", "/api/sidecar/health"),
        ("GET", "/api/model/status"),
        ("GET", "/api/egress/report"),
    }
    assert ("GET", "/health") in public_paths
    assert ("POST", "/api/precheck") not in public_paths


def test_post_no_token_401_contract(tmp_path):
    manager = CapabilityTokenManager(tmp_path / "sidecar_token")
    manager.generate()
    with pytest.raises(CapabilityTokenError) as exc_info:
        manager.verify_authorization_header(None)
    assert exc_info.value.fail_class == FailClass.CAPABILITY_TOKEN_MISSING
    assert auth_error_payload(exc_info.value)["fail_class"] == "CAPABILITY_TOKEN_MISSING"


def test_post_invalid_token_403_contract(tmp_path):
    manager = CapabilityTokenManager(tmp_path / "sidecar_token")
    manager.generate()
    with pytest.raises(CapabilityTokenError) as exc_info:
        manager.verify_authorization_header("Bearer wrong-token")
    assert exc_info.value.fail_class == FailClass.CAPABILITY_TOKEN_INVALID
    assert auth_error_payload(exc_info.value)["fail_class"] == "CAPABILITY_TOKEN_INVALID"


def test_post_valid_token_200_contract(tmp_path):
    manager = CapabilityTokenManager(tmp_path / "sidecar_token")
    token = manager.generate()
    manager.verify_authorization_header(f"Bearer {token}")


def test_token_file_chmod_600(tmp_path):
    token_path = tmp_path / "sidecar_token"
    manager = CapabilityTokenManager(token_path)
    manager.generate()
    mode = stat.S_IMODE(token_path.stat().st_mode)
    assert mode == 0o600
    manager.clear()
    assert not token_path.exists()
