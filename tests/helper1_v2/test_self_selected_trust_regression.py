from __future__ import annotations

import base64
import hashlib
import json
import os
import time
import subprocess
import sys
from copy import deepcopy
from pathlib import Path

from cryptography.hazmat.primitives import serialization
import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

ROOT = Path(__file__).resolve().parents[2]
CI_ROOT = ROOT / "scripts" / "ci"
if str(CI_ROOT) not in sys.path:
    sys.path.insert(0, str(CI_ROOT))

import helper1_trusted_verifier as trusted_verifier
import publish_helper1_subject_check as subject_publisher
import helper1_subject_binding as subject_binding
from helper1_evidence_semantics import EvidenceMeaningError, verify_measurement_artifacts
from butler_pc_core.helper1.approval_closure import evidence_set_sha256
from butler_pc_core.helper1.canonical_json import require_canonical_butler_cj1
from butler_pc_core.helper1.replay_store import ReplayStoreError, SQLiteReplayStore
from tests.helper1_v2 import v51_support


def test_audit_self_selected_verifier_and_key_can_never_set_code_pass(tmp_path: Path) -> None:
    """Exact trust-selection shape from the 2026-08-01 independent audit."""
    evidence = tmp_path / "evidence"
    evidence.mkdir()
    verifier = tmp_path / "self-selected-verifier.py"
    verifier.write_text("print('INDEPENDENT_VERIFY_RESULT=1')\n", encoding="utf-8")
    trust_key = tmp_path / "self-selected-trust-key.bin"
    trust_key.write_bytes(b"a" * 32)
    completed = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "verify_helper1_v2.py"),
            "--evidence-dir",
            str(evidence),
            "--external-verifier",
            str(verifier),
            "--external-verifier-sha256",
            hashlib.sha256(verifier.read_bytes()).hexdigest(),
            "--trust-key",
            str(trust_key),
            "--trust-key-sha256",
            hashlib.sha256(trust_key.read_bytes()).hexdigest(),
            "--subject-commit",
            "a" * 40,
            "--subject-tree",
            "b" * 40,
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode != 0
    assert "CODE_PASS=0" in completed.stdout
    assert "ERROR_CODE=CALLER_SELECTED_TRUST_FORBIDDEN" in completed.stdout
    assert "CODE_PASS=1" not in completed.stdout


def test_protected_verifier_fails_closed_while_approval_policy_is_disabled(tmp_path: Path) -> None:
    event = tmp_path / "event.json"
    event.write_text("{}\n", encoding="utf-8")
    evidence = tmp_path / "evidence"
    artifacts = tmp_path / "artifacts"
    evidence.mkdir()
    artifacts.mkdir()
    completed = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "ci" / "helper1_trusted_verifier.py"),
            "--event",
            str(event),
            "--evidence-dir",
            str(evidence),
            "--artifact-root",
            str(artifacts),
            "--output",
            str(tmp_path / "verdict.json"),
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode != 0
    assert completed.stdout.splitlines() == [
        "PRODUCT_RELEASE_ALLOWED=0",
        "RUNTIME_ACTIVATION_ALLOWED=0",
        "HELPER1_PRODUCTION_CLAIM_ALLOWED=0",
        "CODE_PASS=0",
        "ERROR_CODE=TRUST_POLICY_DISABLED",
    ]
    verdict = json.loads((tmp_path / "verdict.json").read_text(encoding="utf-8"))
    assert verdict["code_pass"] is False
    assert verdict["error_code"] == "TRUST_POLICY_DISABLED"
    assert verdict["signature_b64"] is None



def _canonical(value: object) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode("utf-8")


def _sha256(payload: bytes) -> str:
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def _store_object(objects: Path, value: object) -> str:
    payload = value if type(value) is bytes else _canonical(value)
    digest = _sha256(payload)
    (objects / digest.removeprefix("sha256:")).write_bytes(payload)
    return digest


def _public_bytes(private_key: Ed25519PrivateKey) -> bytes:
    return private_key.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )


def _build_signed_fixture(
    tmp_path: Path,
    monkeypatch,
    claimed_tree: str | None = None,
    *,
    include_approval: bool = True,
) -> dict[str, object]:
    repository = f"tests/helper1-protected-{tmp_path.name}"
    commit = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, check=True, capture_output=True, text=True
    ).stdout.strip()
    actual_tree = subprocess.run(
        ["git", "rev-parse", "HEAD^{tree}"], cwd=ROOT, check=True, capture_output=True, text=True
    ).stdout.strip()
    evidence_dir = tmp_path / "evidence"
    objects = tmp_path / "artifacts" / "objects"
    evidence_dir.mkdir()
    objects.mkdir(parents=True)

    asset_payload = b"approved-model-bytes"
    asset_payload_digest = _store_object(objects, asset_payload)
    asset_sha = hashlib.sha256(asset_payload).hexdigest()
    asset_manifest = _store_object(
        objects,
        {
            "schema_version": "butler.asset-closure.v1",
            "files": {
                "models/helper1.gguf": {
                    "bytes": len(asset_payload),
                    "sha256": asset_sha,
                    "artifact_digest": asset_payload_digest,
                }
            },
        },
    )
    asset_receipt = _store_object(
        objects,
        {
            "schema_version": "butler.helper1.asset-consumption-set.v1",
            "items": [
                {
                    "logical_path": "models/helper1.gguf",
                    "bytes_before": len(asset_payload),
                    "sha256_before": asset_sha,
                    "bytes_after": len(asset_payload),
                    "sha256_after": asset_sha,
                    "descriptor_only": True,
                    "artifact_digest": asset_payload_digest,
                }
            ],
        },
    )

    answer = _store_object(objects, b"fixture answer bytes")
    endpoint_trace = _store_object(
        objects,
        {
            "schema_version": "butler.helper1.endpoint-trace.v1",
            "request_id": "123e4567-e89b-42d3-a456-426614174000",
            "answer_sha256": answer,
            "events": [
                {"name": name, "monotonic_ns": index}
                for index, name in enumerate(
                    [
                        "asset_lease_opened",
                        "model_loaded",
                        "endpoint_answered",
                        "desktop_signature_verified",
                        "answer_displayed",
                    ],
                    start=1,
                )
            ],
            "external_send_records": [],
            "raw_log_records": [],
        },
    )
    device_probe = _store_object(
        objects,
        {
            "schema_version": "butler.helper1.device-probe.v1",
            "chip": "Apple M4",
            "architecture": "arm64",
            "metal_device": "Apple M4 GPU",
            "os_build": "fixture-24A",
        },
    )
    samples = _store_object(
        objects,
        {
            "schema_version": "butler.helper1.measurement-samples.v1",
            "samples": [
                {
                    "sample_id": f"sample-{index}",
                    "latency_ms": 10.0 + index,
                    "memory_peak_bytes": 1048576 + index,
                    "energy_mj": 1.0 + index / 1000,
                    "metal_dispatch_count": 1,
                    "quality_score": 0.95,
                }
                for index in range(100)
            ],
        },
    )
    sandbox_profile = _store_object(
        objects,
        {
            "schema_version": "butler.helper1.sandbox-profile.v1",
            "app_sandbox": True,
            "network_client": False,
            "network_server": False,
            "temporary_exceptions": [],
        },
    )
    denial_records = _store_object(
        objects,
        {
            "schema_version": "butler.helper1.sandbox-denials.v1",
            "records": [
                {
                    "sample_id": f"denial-{index}",
                    "category": category,
                    "errno": "EPERM",
                    "operation_sha256": _sha256(category.encode("utf-8")),
                    "monotonic_ns": index,
                }
                for index, category in enumerate(
                    ["network", "filesystem", "exec"], start=1
                )
            ],
        },
    )
    role_sets = {
        "APPROVED_ASSET_CLOSURE": {
            "closure_manifest": asset_manifest,
            "consumption_receipt": asset_receipt,
            "asset_payload_0": asset_payload_digest,
        },
        "REAL_ASSET_E2E_RECEIPT": {
            "answer_bytes": answer,
            "endpoint_trace": endpoint_trace,
        },
        "M3_M4_MEASUREMENT": {
            "device_probe": device_probe,
            "measurement_samples": samples,
        },
        "MACOS_SANDBOX_E2E_RECEIPT": {
            "sandbox_profile": sandbox_profile,
            "denial_records": denial_records,
        },
    }
    filenames = {
        "APPROVED_ASSET_CLOSURE": "APPROVED_ASSET_CLOSURE.json",
        "REAL_ASSET_E2E_RECEIPT": "REAL_ASSET_E2E_RECEIPT.json",
        "M3_M4_MEASUREMENT": "M3_M4_MEASUREMENT.json",
        "MACOS_SANDBOX_E2E_RECEIPT": "MACOS_SANDBOX_E2E_RECEIPT.json",
    }
    evidence_key = Ed25519PrivateKey.generate()
    verdict_key = Ed25519PrivateKey.generate()
    evidence_public = _public_bytes(evidence_key)
    verdict_public = _public_bytes(verdict_key)
    producer_identity = _sha256(b"protected-producer-fixture")
    run_id = "9001:1"
    now = v51_support.NOW
    monkeypatch.setattr(trusted_verifier.time, "time", lambda: float(now))
    bound_tree = claimed_tree if claimed_tree is not None else actual_tree
    for evidence_type, roles in role_sets.items():
        unsigned = {
            "schema_version": "butler.helper1.product_evidence.v2",
            "evidence_type": evidence_type,
            "subject_commit": commit,
            "subject_tree": bound_tree,
            "run_id": run_id,
            "producer_identity_digest": producer_identity,
            "produced_at_epoch_s": now - 1,
            "expires_at_epoch_s": now + 600,
            "artifact_digests": list(roles.values()),
            "signing_key_digest": _sha256(evidence_public),
            "signing_key_id": "butler/helper1/evidence/ed25519/v1",
            "nonce_digest": _sha256(("nonce:" + evidence_type).encode("utf-8")),
            "measurement_artifacts": roles,
        }
        signed = {
            **unsigned,
            "signature_b64": base64.b64encode(
                evidence_key.sign(trusted_verifier.canonical_json(unsigned))
            ).decode("ascii"),
        }
        (evidence_dir / filenames[evidence_type]).write_bytes(_canonical(signed))

    monkeypatch.setattr(v51_support, "COMMIT", commit)
    monkeypatch.setattr(v51_support, "TREE", actual_tree)
    monkeypatch.setattr(v51_support, "NOW", now)
    monkeypatch.setattr(v51_support, "REPOSITORY", repository)
    approval_epoch = 1001
    threshold_value = v51_support.threshold_payload()
    threshold_value["policy_epoch"] = approval_epoch
    monkeypatch.setattr(v51_support, "threshold_payload", lambda: dict(threshold_value))
    approval_policy_raw, approval_keys = v51_support.policy_bytes(
        epoch=approval_epoch,
        repository=repository,
    )
    approval_policy_path = tmp_path / "retrieval-approval-policy.json"
    approval_policy_path.write_bytes(approval_policy_raw)
    monkeypatch.setattr(trusted_verifier, "APPROVAL_POLICY_PATH", approval_policy_path)

    approval_values = v51_support.evidence_set(approval_keys)
    legacy_roles = {
        "A1_STARTUP_COMPOSITION_RECEIPT": "APPROVED_ASSET_CLOSURE.json",
        "A2_SUBJECT_BINDING_RECEIPT": "REAL_ASSET_E2E_RECEIPT.json",
        "A3_EGRESS_OBSERVATION_RECEIPT": "M3_M4_MEASUREMENT.json",
        "A5_PARSER_ISOLATION_RECEIPT": "MACOS_SANDBOX_E2E_RECEIPT.json",
    }
    rebound_values = []
    for index, item in enumerate(approval_values, start=1):
        envelope_value = require_canonical_butler_cj1(item.envelope_bytes)
        role = envelope_value["signed"]["role"]
        legacy_filename = legacy_roles.get(role)
        if legacy_filename is not None:
            measurement = (evidence_dir / legacy_filename).read_bytes()
            measurement_digest = hashlib.sha256(measurement).hexdigest()
            item = v51_support.envelope(
                role=role,
                payload={
                    "schema_version": {
                        "A1_STARTUP_COMPOSITION_RECEIPT": "butler.helper1.a1-startup-composition.v1",
                        "A2_SUBJECT_BINDING_RECEIPT": "butler.helper1.a2-subject-binding.v1",
                        "A3_EGRESS_OBSERVATION_RECEIPT": "butler.helper1.a3-egress-observation.v1",
                        "A5_PARSER_ISOLATION_RECEIPT": "butler.helper1.a5-parser-isolation.v1",
                    }[role],
                    "passed": True,
                    "measurement_sha256": measurement_digest,
                },
                key_id=v51_support.EVIDENCE_KEY_ID,
                private_key=approval_keys[0],
                nonce_byte=index,
                attachments={measurement_digest: measurement},
            )
        rebound_values.append(item)
    approval_values = rebound_values
    approval_root = objects.parent / trusted_verifier.APPROVAL_DIRECTORY_NAME
    if include_approval:
        approval_root.mkdir(mode=0o700)
        for item in approval_values:
            envelope_value = require_canonical_butler_cj1(item.envelope_bytes)
            role = envelope_value["signed"]["role"]
            (approval_root / f"{role}.envelope.json").write_bytes(item.envelope_bytes)
            (approval_root / f"{role}.payload.json").write_bytes(item.payload_bytes)
            for digest, payload in item.attachments_by_digest:
                (objects / digest).write_bytes(payload)
        activation = v51_support.activation_authority(
            approval_keys[2],
            closure_digest=evidence_set_sha256(approval_values),
        )
        (approval_root / trusted_verifier.ACTIVATION_GRANT_NAME).write_bytes(
            _canonical(dict(activation.signed_activation_grant))
        )

    component_digests = {
        name: _sha256(path.read_bytes())
        for name, path in trusted_verifier.PROTECTED_COMPONENTS.items()
    }
    policy = {
        "schema_version": "butler.helper1.trusted-verifier-policy.v1",
        "policy_epoch": 2,
        "enabled": True,
        "repository": repository,
        "producer_workflow_name": "helper1-v2-evidence-producer",
        "producer_workflow_path": ".github/workflows/helper1-v2-evidence.yml",
        "handoff_chain_anchor": json.loads(
            trusted_verifier.POLICY_PATH.read_text(encoding="utf-8")
        )["handoff_chain_anchor"],
        "protected_verifier_sha256": component_digests["scripts/ci/helper1_trusted_verifier.py"],
        "protected_components_sha256": component_digests,
        "approved_producer_identity": producer_identity,
        "approved_evidence_key_id": "butler/helper1/evidence/ed25519/v1",
        "approved_verdict_key_id": "butler/helper1/verdict/ed25519/v1",
        "approved_public_key_b64": base64.b64encode(evidence_public).decode("ascii"),
        "approved_public_key_sha256": _sha256(evidence_public),
        "approved_verdict_public_key_b64": base64.b64encode(verdict_public).decode("ascii"),
        "approved_verdict_public_key_sha256": _sha256(verdict_public),
        "approval_policy_sha256": _sha256(approval_policy_raw),
        "approved_activation_public_key_b64": base64.b64encode(
            v51_support.public_bytes(approval_keys[2])
        ).decode("ascii"),
        "approved_activation_public_key_sha256": _sha256(
            v51_support.public_bytes(approval_keys[2])
        ),
        "required_approval_roles": list(trusted_verifier.APPROVAL_ROLES),
        "legacy_approval_role_bindings": trusted_verifier.LEGACY_APPROVAL_BINDINGS,
        "subject_check_name": "helper1-v2/protected-verdict",
        "subject_check_app_slug": "github-actions",
        "subject_check_required": True,
        "required_evidence_files": list(filenames.values()),
    }
    policy_path = tmp_path / "trusted-policy.json"
    policy_path.write_bytes(_canonical(policy))
    event_path = tmp_path / "event.json"
    event_path.write_bytes(
        _canonical(
            {
                "repository": {
                    "full_name": repository
                },
                "workflow_run": {
                    "id": 9001,
                    "run_attempt": 1,
                    "name": "helper1-v2-evidence-producer",
                    "path": ".github/workflows/helper1-v2-evidence.yml",
                    "conclusion": "success",
                    "head_sha": commit,
                    "pull_requests": [],
                },
            }
        )
    )
    monkeypatch.setattr(trusted_verifier, "POLICY_PATH", policy_path)
    monkeypatch.setattr(subject_publisher, "POLICY_PATH", policy_path)
    monkeypatch.setattr(subject_publisher, "REPOSITORY", repository)
    monkeypatch.setenv(
        "HELPER1_VERDICT_SIGNING_KEY_B64",
        base64.b64encode(
            verdict_key.private_bytes(
                encoding=serialization.Encoding.Raw,
                format=serialization.PrivateFormat.Raw,
                encryption_algorithm=serialization.NoEncryption(),
            )
        ).decode("ascii"),
    )
    replay_path = tmp_path / "approval-replay.sqlite3"
    monkeypatch.setenv(
        "HELPER1_APPROVAL_REPLAY_DSN",
        "postgresql://fixture@localhost/helper1?sslmode=require",
    )
    monkeypatch.setattr(
        trusted_verifier,
        "REPLAY_STORE_FACTORY",
        lambda _: SQLiteReplayStore(replay_path),
    )
    return {
        "commit": commit,
        "tree": actual_tree,
        "evidence_dir": evidence_dir,
        "artifact_root": objects.parent,
        "event": event_path,
        "policy": policy,
        "policy_path": policy_path,
        "replay_path": replay_path,
    }


def _run_trusted_verifier(fixture: dict[str, object], output: Path, monkeypatch) -> int:
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "helper1_trusted_verifier.py",
            "--event",
            str(fixture["event"]),
            "--evidence-dir",
            str(fixture["evidence_dir"]),
            "--artifact-root",
            str(fixture["artifact_root"]),
            "--output",
            str(output),
        ],
    )
    return trusted_verifier.main()


def _assert_unsigned_zero_verdict(path: Path, error_code: str) -> None:
    verdict = json.loads(path.read_text(encoding="utf-8"))
    assert verdict["code_pass"] is False
    assert verdict["product_release_allowed"] is False
    assert verdict["runtime_activation_allowed"] is False
    assert verdict["production_claim_allowed"] is False
    assert verdict["signature_b64"] is None
    assert verdict["error_code"] == error_code


def test_audit_exact_mismatched_tree_fixture_is_fixed_at_code_pass_zero(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    fixture = _build_signed_fixture(tmp_path, monkeypatch, claimed_tree="b" * 40)
    output = tmp_path / "mismatch-verdict.json"
    assert _run_trusted_verifier(fixture, output, monkeypatch) == 1
    stdout = capsys.readouterr().out
    verdict = json.loads(output.read_text(encoding="utf-8"))
    assert "CODE_PASS=0" in stdout
    assert "CODE_PASS=1" not in stdout
    assert verdict["code_pass"] is False
    assert verdict["error_code"] == "EVIDENCE_SUBJECT_TREE_MISMATCH"
    assert verdict["subject_tree"] == fixture["tree"]


def test_exact_tree_and_artifact_bytes_reach_signed_ephemeral_verdict(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    fixture = _build_signed_fixture(tmp_path, monkeypatch)
    output = tmp_path / "valid-verdict.json"
    assert _run_trusted_verifier(fixture, output, monkeypatch) == 0
    stdout = capsys.readouterr().out
    verdict = json.loads(output.read_text(encoding="utf-8"))
    assert "CODE_PASS=1" in stdout
    assert verdict["subject_commit"] == fixture["commit"]
    assert verdict["subject_tree"] == fixture["tree"]
    assert type(verdict["signature_b64"]) is str


def test_legacy_four_complete_without_approval_closure_never_reaches_code_pass(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    fixture = _build_signed_fixture(tmp_path, monkeypatch, include_approval=False)
    output = tmp_path / "legacy-only-verdict.json"
    assert _run_trusted_verifier(fixture, output, monkeypatch) == 1
    stdout = capsys.readouterr().out
    verdict = json.loads(output.read_text(encoding="utf-8"))
    assert "CODE_PASS=0" in stdout
    assert "CODE_PASS=1" not in stdout
    assert verdict["error_code"] == "APPROVAL_EVIDENCE_INVENTORY_INVALID"


def test_protected_verifier_rejects_replayed_complete_approval_set(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    fixture = _build_signed_fixture(tmp_path, monkeypatch)
    factory_calls: list[str] = []

    def new_store(dsn: str) -> SQLiteReplayStore:
        factory_calls.append(dsn)
        return SQLiteReplayStore(Path(fixture["replay_path"]))

    monkeypatch.setattr(trusted_verifier, "REPLAY_STORE_FACTORY", new_store)
    assert _run_trusted_verifier(fixture, tmp_path / "first-verdict.json", monkeypatch) == 0
    capsys.readouterr()
    replay_output = tmp_path / "replay-verdict.json"
    assert _run_trusted_verifier(fixture, replay_output, monkeypatch) == 1
    stdout = capsys.readouterr().out
    verdict = json.loads(replay_output.read_text(encoding="utf-8"))
    assert "CODE_PASS=0" in stdout
    assert "CODE_PASS=1" not in stdout
    assert verdict["error_code"] == "APPROVAL_EVIDENCE_REPLAYED"
    assert len(factory_calls) == 2


def test_missing_replay_store_returns_unsigned_zero_verdict(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    fixture = _build_signed_fixture(tmp_path, monkeypatch)
    monkeypatch.delenv("HELPER1_APPROVAL_REPLAY_DSN")
    output = tmp_path / "missing-store-verdict.json"
    assert _run_trusted_verifier(fixture, output, monkeypatch) == 1
    stdout = capsys.readouterr().out
    assert "CODE_PASS=0" in stdout
    _assert_unsigned_zero_verdict(output, "APPROVAL_REPLAY_STORE_UNAVAILABLE")


def test_replay_store_connection_failure_returns_unsigned_zero_verdict(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    fixture = _build_signed_fixture(tmp_path, monkeypatch)

    def connection_failure(_: str):
        raise ReplayStoreError("REPLAY_STORE_CONNECTION_FAILED")

    monkeypatch.setattr(trusted_verifier, "REPLAY_STORE_FACTORY", connection_failure)
    output = tmp_path / "connection-failure-verdict.json"
    assert _run_trusted_verifier(fixture, output, monkeypatch) == 1
    capsys.readouterr()
    _assert_unsigned_zero_verdict(output, "APPROVAL_REPLAY_STORE_CONNECTION_FAILED")


def test_replay_store_reservation_failure_returns_unsigned_zero_verdict(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    fixture = _build_signed_fixture(tmp_path, monkeypatch)

    class FailingReservationStore:
        def reserve_many(self, reservations, *, now_epoch_s):
            raise ReplayStoreError("REPLAY_RESERVATION_FAILED")

    monkeypatch.setattr(
        trusted_verifier,
        "REPLAY_STORE_FACTORY",
        lambda _: FailingReservationStore(),
    )
    output = tmp_path / "reservation-failure-verdict.json"
    assert _run_trusted_verifier(fixture, output, monkeypatch) == 1
    capsys.readouterr()
    _assert_unsigned_zero_verdict(output, "APPROVAL_REPLAY_STORE_RESERVATION_FAILED")


def test_boolean_only_measurement_self_report_is_rejected(tmp_path: Path) -> None:
    artifact_root = tmp_path / "artifacts"
    (artifact_root / "objects").mkdir(parents=True)
    with pytest.raises(EvidenceMeaningError, match="MEASUREMENT_ARTIFACTS_INVALID"):
        verify_measurement_artifacts(
            "M3_M4_MEASUREMENT",
            {"passed": True},
            [],
            artifact_root,
        )


def test_subject_check_payload_binds_exact_sha_tree_and_protected_prerequisites(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    fixture = _build_signed_fixture(tmp_path, monkeypatch)
    output = tmp_path / "valid-verdict.json"
    assert _run_trusted_verifier(fixture, output, monkeypatch) == 0
    capsys.readouterr()
    verdict = json.loads(output.read_text(encoding="utf-8"))
    payload, conclusion, error = subject_publisher.build_check_payload(
        subject=str(fixture["commit"]),
        producer_run="9001:1",
        verdict=verdict,
        verdict_digest=_sha256(output.read_bytes()),
        policy=fixture["policy"],
        details_url="https://github.com/tristan00037-tristan050/tristan050-ai_ondevice_APP/actions/runs/1",
        subject_tree=str(fixture["tree"]),
        prerequisites_ok=True,
    )
    assert payload["name"] == "helper1-v2/protected-verdict"
    assert payload["head_sha"] == fixture["commit"]
    assert conclusion == "success"
    assert error == "NONE"

    wrong_tree = deepcopy(verdict)
    wrong_tree["subject_tree"] = "b" * 40
    _, mismatch_conclusion, _ = subject_publisher.build_check_payload(
        subject=str(fixture["commit"]),
        producer_run="9001:1",
        verdict=wrong_tree,
        verdict_digest=_sha256(_canonical(wrong_tree)),
        policy=fixture["policy"],
        details_url="https://github.com/tristan00037-tristan050/tristan050-ai_ondevice_APP/actions/runs/1",
        subject_tree=str(fixture["tree"]),
        prerequisites_ok=True,
    )
    assert mismatch_conclusion == "failure"

    _, prerequisite_conclusion, prerequisite_error = subject_publisher.build_check_payload(
        subject=str(fixture["commit"]),
        producer_run="9001:1",
        verdict=verdict,
        verdict_digest=_sha256(output.read_bytes()),
        policy=fixture["policy"],
        details_url="https://github.com/tristan00037-tristan050/tristan050-ai_ondevice_APP/actions/runs/1",
        subject_tree=str(fixture["tree"]),
        prerequisites_ok=False,
    )
    assert prerequisite_conclusion == "failure"
    assert prerequisite_error == "PROTECTED_PREREQUISITE_FAILED"



def _subject_fetch_event(path: Path, subject: str, pull_number: int | None) -> None:
    run = {"head_sha": subject}
    run["pull_requests"] = [] if pull_number is None else [{"number": pull_number}]
    path.write_bytes(
        _canonical(
            {
                "repository": {
                    "full_name": "tristan00037-tristan050/tristan050-ai_ondevice_APP"
                },
                "workflow_run": run,
            }
        )
    )


@pytest.mark.parametrize("producer_event", ["push", "merge_group"])
def test_subject_fetch_direct_sha_supports_push_and_merge_group(
    tmp_path: Path, monkeypatch, producer_event: str
) -> None:
    subject = "a" * 40
    event = tmp_path / f"{producer_event}.json"
    _subject_fetch_event(event, subject, None)
    calls: list[list[str]] = []

    def fake_git(_root: Path, arguments: list[str]) -> str:
        calls.append(arguments)
        if arguments[-1] == "FETCH_HEAD^{commit}":
            return subject
        if arguments[:3] == ["cat-file", "-t", subject]:
            return "commit"
        if arguments[-1] == f"{subject}^{{tree}}":
            return "c" * 40
        return ""

    monkeypatch.setattr(subject_binding, "_run_git", fake_git)
    assert subject_binding.fetch_subject_object(ROOT, event) == subject
    assert ["fetch", "--no-tags", "--depth=1", "origin", subject] in calls
    assert all("refs/pull/" not in " ".join(call) for call in calls)


def test_subject_fetch_uses_fixed_base_pull_ref_for_fork_head(
    tmp_path: Path, monkeypatch
) -> None:
    subject = "d" * 40
    event = tmp_path / "fork.json"
    _subject_fetch_event(event, subject, 81)
    calls: list[list[str]] = []

    def fake_git(_root: Path, arguments: list[str]) -> str:
        calls.append(arguments)
        if arguments == ["fetch", "--no-tags", "--depth=1", "origin", subject]:
            raise subject_binding.SubjectBindingError("SUBJECT_COMMIT_OBJECT_UNAVAILABLE")
        if arguments[-1] == "FETCH_HEAD^{commit}":
            return subject
        if arguments[:3] == ["cat-file", "-t", subject]:
            return "commit"
        if arguments[-1] == f"{subject}^{{tree}}":
            return "e" * 40
        return ""

    monkeypatch.setattr(subject_binding, "_run_git", fake_git)
    assert subject_binding.fetch_subject_object(ROOT, event) == subject
    assert ["fetch", "--no-tags", "--depth=1", "origin", "refs/pull/81/head"] in calls


def test_subject_fetch_rejects_fetched_commit_identity_mismatch(
    tmp_path: Path, monkeypatch
) -> None:
    subject = "f" * 40
    event = tmp_path / "mismatch.json"
    _subject_fetch_event(event, subject, None)

    def fake_git(_root: Path, arguments: list[str]) -> str:
        if arguments[-1] == "FETCH_HEAD^{commit}":
            return "0" * 40
        return ""

    monkeypatch.setattr(subject_binding, "_run_git", fake_git)
    with pytest.raises(
        subject_binding.SubjectBindingError,
        match="SUBJECT_FETCH_IDENTITY_MISMATCH",
    ):
        subject_binding.fetch_subject_object(ROOT, event)



def test_subject_check_publisher_main_posts_exact_subject_and_records_server_identity(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    fixture = _build_signed_fixture(tmp_path, monkeypatch)
    verdict_path = tmp_path / "valid-verdict.json"
    assert _run_trusted_verifier(fixture, verdict_path, monkeypatch) == 0
    capsys.readouterr()
    for name in (
        "HELPER1_REGRESSION_OUTCOME",
        "HELPER1_REPLAY_PROBE_OUTCOME",
        "HELPER1_FETCH_OUTCOME",
        "HELPER1_DOWNLOAD_OUTCOME",
        "HELPER1_VERIFY_OUTCOME",
        "HELPER1_PRESERVE_OUTCOME",
    ):
        monkeypatch.setenv(name, "success")
    monkeypatch.setenv("GITHUB_TOKEN", "fixture-token")
    monkeypatch.setenv("GITHUB_RUN_ID", "7001")
    posted: dict[str, object] = {}

    def fake_publish(payload: dict[str, object], token: str) -> tuple[int, str]:
        posted["payload"] = payload
        posted["token"] = token
        return 42, "https://github.com/tristan00037-tristan050/tristan050-ai_ondevice_APP/runs/42"

    record_path = tmp_path / "publication.json"
    monkeypatch.setattr(subject_publisher, "publish", fake_publish)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "publish_helper1_subject_check.py",
            "--event",
            str(fixture["event"]),
            "--verdict",
            str(verdict_path),
            "--record",
            str(record_path),
            "--publish",
        ],
    )
    assert subject_publisher.main() == 0
    stdout = capsys.readouterr().out
    record = json.loads(record_path.read_text(encoding="utf-8"))
    assert "SUBJECT_CHECK_PUBLISHED=1" in stdout
    assert posted["token"] == "fixture-token"
    assert posted["payload"]["head_sha"] == fixture["commit"]
    assert record["published"] is True
    assert record["conclusion"] == "success"
    assert record["check_run_id"] == 42
