"""FirstScreen v2.5 in-process trust-chain compatibility entry-point tests."""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from butler_pc_core.firstscreen_trust import (
    BootstrapRoot,
    TrustVerificationError,
    document_digest,
    key_id_for_public_key,
    sign_document,
)


pytestmark = pytest.mark.no_sidecar_token

# 이 파일의 시험은 검증기를 subprocess 로 부르므로 검증기가 ★실제 현재 시각으로 판정한다.
# (CLI 에 시각 주입 수단이 없다 — 만료 검사를 무력화하지 않기 위해 일부러 두지 않는다.)
# 따라서 문서의 유효기간은 절대 날짜로 박으면 안 되고 실행 시각 기준 상대값으로 만든다.
# 절대 날짜로 박으면 그 날이 지나는 순간 저장소 전체가 막힌다(2026-08-01 사고).


def _stamp(delta: timedelta) -> str:
    return (datetime.now(timezone.utc) + delta).strftime("%Y-%m-%dT%H:%M:%SZ")


def _verdict(key: str, passed: bool, error_code: str | None = None) -> str:
    result = f"{key}_OK={int(passed)}"
    return f"{result} ERROR_CODE={error_code}" if error_code else result


def _key() -> tuple[Ed25519PrivateKey, str, str]:
    private = Ed25519PrivateKey.generate()
    raw = private.public_key().public_bytes_raw()
    import base64

    return private, key_id_for_public_key(raw), base64.urlsafe_b64encode(raw).decode().rstrip("=")


def _write(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")), encoding="utf-8")


def _chain(
    tmp_path: Path,
    *,
    decision_approved: timedelta = timedelta(days=-1),
    decision_expires: timedelta = timedelta(days=30),
) -> dict[str, Path]:
    root_private, root_id, root_public = _key()
    risk_private, risk_id, risk_public = _key()
    rev_private, rev_id, rev_public = _key()
    release_private, release_id, release_public = _key()
    root = {
        "schema_version": "butler.firstscreen.root-policy.v1",
        "policy_id": "butler-firstscreen-trust",
        "version": 1,
        "expires_at_utc": _stamp(timedelta(days=365)),
        "consistent_snapshot": True,
        "keys": {
            root_id: {"algorithm": "ed25519", "public_key": root_public},
            risk_id: {"algorithm": "ed25519", "public_key": risk_public},
            rev_id: {"algorithm": "ed25519", "public_key": rev_public},
            release_id: {"algorithm": "ed25519", "public_key": release_public},
        },
        "roles": {
            "root": {"key_ids": [root_id], "threshold": 1},
            "risk-decision": {"key_ids": [risk_id], "threshold": 1},
            "revocation": {"key_ids": [rev_id], "threshold": 1},
            "release": {"key_ids": [release_id], "threshold": 1},
        },
        "previous_root_digest": None,
        "signatures": [],
    }
    root["signatures"] = [sign_document("root-policy", root, root_private, root_id)]
    root_digest = document_digest(root)
    revocations = {
        "schema_version": "butler.firstscreen.revocations.v2",
        "policy_id": "butler-firstscreen-trust",
        "version": 1,
        "generated_at_utc": _stamp(timedelta(days=-1)),
        "expires_at_utc": _stamp(timedelta(days=30)),
        "previous_digest": None,
        "root_policy_digest": root_digest,
        "revoked_decision_ids": [],
        "revoked_key_ids": [],
        "revoked_epochs": [],
        "signatures": [],
    }
    revocations["signatures"] = [sign_document("revocations", revocations, rev_private, rev_id)]
    decision = {
        "schema_version": "butler.firstscreen.risk-decision.v2",
        "policy_id": "butler-firstscreen-trust",
        "decision_id": "STORAGE_RISK_FS_V2_5_001",
        "version": 1,
        "approved_at_utc": _stamp(decision_approved),
        "expires_at_utc": _stamp(decision_expires),
        "scope": ["CONVERSATION_TITLE", "FTS_TITLE_INDEX"],
        "protection_boundary": ["ON_DEVICE", "OS_USER_BOUNDARY", "APP_DATA_PATH", "OWNER_MODE_GUARD"],
        "data_classification": "CONFIDENTIAL",
        "owner_role": "ATLINK_REPRESENTATIVE",
        "revocation_epoch": 0,
        "root_policy_digest": root_digest,
        "source_blob_digest": "a" * 64,
        "canonical_ssot_location": "docs/product/firstscreen_v2_5/risk-decision.json",
        "signatures": [],
    }
    decision["signatures"] = [sign_document("risk-decision", decision, risk_private, risk_id)]
    paths = {name: tmp_path / f"{name}.json" for name in ("bootstrap", "root", "revocations", "decision")}
    _write(
        paths["bootstrap"],
        {
            "schema_version": "butler.firstscreen.bootstrap.v1",
            "policy_digest": root_digest,
            "minimum_root_version": 1,
            "minimum_revocation_version": 1,
            "authority": "OFFLINE_CONSUMER",
        },
    )
    _write(paths["root"], root)
    _write(paths["revocations"], revocations)
    _write(paths["decision"], decision)
    return paths


def _run(root: Path, paths: dict[str, Path]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            sys.executable,
            "scripts/verify/verify_storage_risk_acceptance.py",
            "--bootstrap",
            str(paths["bootstrap"]),
            "--root",
            str(paths["root"]),
            "--revocations",
            str(paths["revocations"]),
            "--decision",
            str(paths["decision"]),
        ],
        cwd=root,
        text=True,
        capture_output=True,
        check=False,
        timeout=10,
        env={**__import__("os").environ, "PYTHONPATH": str(root)},
    )


def test_in_process_chain_passes_without_ssh_keygen(tmp_path: Path) -> None:
    root = Path(__file__).resolve().parents[1]
    completed = _run(root, _chain(tmp_path))
    assert completed.returncode == 0
    assert completed.stdout.strip() == _verdict("STORAGE_RISK_ACCEPTANCE", True)
    assert completed.stderr == ""


def _load_verifier(repository_root: Path):
    spec = importlib.util.spec_from_file_location(
        "_verify_storage_risk_acceptance",
        repository_root / "scripts/verify/verify_storage_risk_acceptance.py",
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_expired_decision_is_blocked(tmp_path: Path) -> None:
    """만료 검사가 실제로 도는지 확인한다.

    유효기간을 상대 시각으로 만들면 정상 시험은 언제 돌려도 통과한다. 그것만으로는
    ★만료 검사가 살아 있는지 알 수 없으므로, 이미 만료된 결정서를 만들어 차단되는지
    반대 방향으로 확인한다.
    """
    repository_root = Path(__file__).resolve().parents[1]
    paths = _chain(
        tmp_path,
        decision_approved=timedelta(days=-2),
        decision_expires=timedelta(days=-1),
    )

    # CLI 는 fail-closed 로 떨어진다.
    completed = _run(repository_root, paths)
    assert completed.returncode == 1
    assert completed.stdout.strip() == _verdict(
        "STORAGE_RISK_ACCEPTANCE", False, "STORAGE_RISK_ACCEPTANCE_INVALID"
    )
    assert completed.stderr == ""

    # CLI 는 사유를 일반 코드로 가리므로, 차단 사유가 ★만료인지 라이브러리로 확인한다.
    module = _load_verifier(repository_root)
    with pytest.raises(TrustVerificationError) as raised:
        module.verify_installed_policy(
            bootstrap=paths["bootstrap"].resolve(),
            root=paths["root"].resolve(),
            revocations=paths["revocations"].resolve(),
            decision=paths["decision"].resolve(),
        )
    assert str(raised.value) == "BLOCK_DECISION_EXPIRED"


@pytest.mark.parametrize("artifact", ["bootstrap", "root", "revocations", "decision"])
def test_missing_chain_member_fails_closed(tmp_path: Path, artifact: str) -> None:
    root = Path(__file__).resolve().parents[1]
    paths = _chain(tmp_path)
    paths[artifact].unlink()
    completed = _run(root, paths)
    assert completed.returncode == 1
    assert completed.stdout.strip() == _verdict(
        "STORAGE_RISK_ACCEPTANCE", False, "STORAGE_RISK_ACCEPTANCE_INVALID"
    )
    assert completed.stderr == ""


def test_repository_has_no_owner_policy_and_remains_blocked() -> None:
    root = Path(__file__).resolve().parents[1]
    policy = root / "docs/product/firstscreen_v2_5/trust"
    assert not (policy / "bootstrap.json").exists()
    assert not (policy / "root-policy.json").exists()
