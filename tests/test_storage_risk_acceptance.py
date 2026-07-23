"""FirstScreen v2.5 in-process trust-chain compatibility entry-point tests."""

from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from butler_pc_core.firstscreen_trust import (
    BootstrapRoot,
    document_digest,
    key_id_for_public_key,
    sign_document,
)


pytestmark = pytest.mark.no_sidecar_token
NOW = datetime(2026, 7, 21, 12, 0, 0, tzinfo=timezone.utc)


def _key() -> tuple[Ed25519PrivateKey, str, str]:
    private = Ed25519PrivateKey.generate()
    raw = private.public_key().public_bytes_raw()
    import base64

    return private, key_id_for_public_key(raw), base64.urlsafe_b64encode(raw).decode().rstrip("=")


def _write(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")), encoding="utf-8")


def _chain(tmp_path: Path) -> dict[str, Path]:
    root_private, root_id, root_public = _key()
    risk_private, risk_id, risk_public = _key()
    rev_private, rev_id, rev_public = _key()
    release_private, release_id, release_public = _key()
    root = {
        "schema_version": "butler.firstscreen.root-policy.v1",
        "policy_id": "butler-firstscreen-trust",
        "version": 1,
        "expires_at_utc": "2027-07-21T00:00:00Z",
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
        "generated_at_utc": "2026-07-21T00:00:00Z",
        "expires_at_utc": "2026-08-21T00:00:00Z",
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
        "approved_at_utc": "2026-07-21T00:00:00Z",
        "expires_at_utc": "2026-08-01T00:00:00Z",
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
    assert completed.stdout.strip() == "STORAGE_RISK_ACCEPTANCE_OK=1"
    assert completed.stderr == ""


@pytest.mark.parametrize("artifact", ["bootstrap", "root", "revocations", "decision"])
def test_missing_chain_member_fails_closed(tmp_path: Path, artifact: str) -> None:
    root = Path(__file__).resolve().parents[1]
    paths = _chain(tmp_path)
    paths[artifact].unlink()
    completed = _run(root, paths)
    assert completed.returncode == 1
    assert completed.stdout.strip() == "STORAGE_RISK_ACCEPTANCE_OK=0 ERROR_CODE=STORAGE_RISK_ACCEPTANCE_INVALID"
    assert completed.stderr == ""


def test_repository_has_no_owner_policy_and_remains_blocked() -> None:
    root = Path(__file__).resolve().parents[1]
    policy = root / "docs/product/firstscreen_v2_5/trust"
    assert not (policy / "bootstrap.json").exists()
    assert not (policy / "root-policy.json").exists()
