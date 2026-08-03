from __future__ import annotations

from copy import deepcopy
import hashlib

from butler_pc_core.helper1.approval_closure import (
    EvidenceArtifact,
    FailureCode,
    evaluate_product_closure,
    recompute_a4_rows,
)
from butler_pc_core.helper1.canonical_json import require_canonical_butler_cj1

from .v51_support import (
    EVIDENCE_KEY_ID,
    THRESHOLD_KEY_ID,
    activation_authority,
    authority,
    envelope,
    evaluation_material,
    evidence_set,
    evidence_set_digest,
    rows,
)


def _payload(item: EvidenceArtifact) -> dict:
    return require_canonical_butler_cj1(item.payload_bytes)


def _role(item: EvidenceArtifact) -> str:
    return require_canonical_butler_cj1(item.envelope_bytes)["signed"]["role"]


def _evaluate(tmp_path, values, keys):
    policy_authority, _ = authority(tmp_path)
    activation = activation_authority(keys[2], closure_digest=evidence_set_digest(values))
    return evaluate_product_closure(policy_authority, activation, values)


def test_false_abstention_remains_in_precision_denominator() -> None:
    counts, metrics, _ = recompute_a4_rows(rows("audit"))
    assert counts["predicted_abstention_count"] == 2
    assert counts["false_abstention_count"] == 1
    assert metrics["abstention_precision_ppm"] == 500_000
    assert metrics["abstention_recall_ppm"] == 500_000


def test_each_missing_a4_receipt_has_the_specific_missing_code(tmp_path) -> None:
    _, keys = authority(tmp_path / "keys")
    for role in (
        "A4_RETRIEVAL_CALIBRATION_RECEIPT",
        "A4_RETRIEVAL_SEALED_TEST_RECEIPT",
    ):
        values = [item for item in evidence_set(keys) if _role(item) != role]
        verdict = _evaluate(tmp_path / role, values, keys)
        assert any(
            item.code is FailureCode.A4_EVIDENCE_MISSING and item.role == role
            for item in verdict.failures
        )


def test_recomputed_metric_mismatch_blocks_even_when_resigned(tmp_path) -> None:
    _, keys = authority(tmp_path / "keys")
    values = evidence_set(keys)
    index = next(i for i, item in enumerate(values) if _role(item) == "A4_RETRIEVAL_CALIBRATION_RECEIPT")
    target = values[index]
    payload = deepcopy(_payload(target))
    payload["metrics_ppm"]["retrieval_recall_ppm"] = 1_000_000
    values[index] = envelope(
        role="A4_RETRIEVAL_CALIBRATION_RECEIPT",
        payload=payload,
        key_id=EVIDENCE_KEY_ID,
        private_key=keys[0],
        nonce_byte=77,
        attachments=dict(target.attachments_by_digest),
    )
    verdict = _evaluate(tmp_path / "eval", values, keys)
    assert FailureCode.A4_METRIC_RECOMPUTE_MISMATCH in {item.code for item in verdict.failures}


def test_calibration_and_sealed_cross_binding_is_enforced(tmp_path) -> None:
    _, keys = authority(tmp_path / "keys")
    values = evidence_set(keys)
    index = next(i for i, item in enumerate(values) if _role(item) == "A4_RETRIEVAL_SEALED_TEST_RECEIPT")
    target = values[index]
    payload = deepcopy(_payload(target))
    payload["calibration_payload_sha256"] = "f" * 64
    values[index] = envelope(
        role="A4_RETRIEVAL_SEALED_TEST_RECEIPT",
        payload=payload,
        key_id=EVIDENCE_KEY_ID,
        private_key=keys[0],
        nonce_byte=78,
        attachments=dict(target.attachments_by_digest),
    )
    verdict = _evaluate(tmp_path / "eval", values, keys)
    assert FailureCode.A4_CROSS_BINDING_MISMATCH in {item.code for item in verdict.failures}


def test_threshold_policy_epoch_must_match_trust_policy_epoch(tmp_path) -> None:
    _, keys = authority(tmp_path / "keys")
    values = evidence_set(keys)
    index = next(i for i, item in enumerate(values) if _role(item) == "A4_RETRIEVAL_THRESHOLD_POLICY")
    target = values[index]
    payload = deepcopy(_payload(target))
    payload["policy_epoch"] = 50
    values[index] = envelope(
        role="A4_RETRIEVAL_THRESHOLD_POLICY",
        payload=payload,
        key_id=THRESHOLD_KEY_ID,
        private_key=keys[1],
        nonce_byte=80,
        attachments=dict(target.attachments_by_digest),
    )
    verdict = _evaluate(tmp_path / "eval", values, keys)
    assert any(
        item.code is FailureCode.A4_CROSS_BINDING_MISMATCH and item.field_path == "policy_epoch"
        for item in verdict.failures
    )


def test_signed_threshold_metric_minimum_is_actually_enforced(tmp_path) -> None:
    _, keys = authority(tmp_path / "keys")
    values = evidence_set(keys)
    threshold_index = next(i for i, item in enumerate(values) if _role(item) == "A4_RETRIEVAL_THRESHOLD_POLICY")
    threshold_target = values[threshold_index]
    threshold_payload = deepcopy(_payload(threshold_target))
    threshold_payload["minimum_metrics_ppm"]["retrieval_recall_ppm"] = 600_000
    values[threshold_index] = envelope(
        role="A4_RETRIEVAL_THRESHOLD_POLICY",
        payload=threshold_payload,
        key_id=THRESHOLD_KEY_ID,
        private_key=keys[1],
        nonce_byte=81,
        attachments=dict(threshold_target.attachments_by_digest),
    )
    threshold_digest = hashlib.sha256(values[threshold_index].payload_bytes).hexdigest()
    calibration_index = next(i for i, item in enumerate(values) if _role(item) == "A4_RETRIEVAL_CALIBRATION_RECEIPT")
    calibration_target = values[calibration_index]
    calibration_payload = deepcopy(_payload(calibration_target))
    calibration_payload["threshold_policy_sha256"] = threshold_digest
    values[calibration_index] = envelope(
        role="A4_RETRIEVAL_CALIBRATION_RECEIPT",
        payload=calibration_payload,
        key_id=EVIDENCE_KEY_ID,
        private_key=keys[0],
        nonce_byte=82,
        attachments=dict(calibration_target.attachments_by_digest),
    )
    sealed_index = next(i for i, item in enumerate(values) if _role(item) == "A4_RETRIEVAL_SEALED_TEST_RECEIPT")
    sealed_target = values[sealed_index]
    sealed_payload = deepcopy(_payload(sealed_target))
    sealed_payload["threshold_policy_sha256"] = threshold_digest
    sealed_payload["calibration_payload_sha256"] = hashlib.sha256(values[calibration_index].payload_bytes).hexdigest()
    values[sealed_index] = envelope(
        role="A4_RETRIEVAL_SEALED_TEST_RECEIPT",
        payload=sealed_payload,
        key_id=EVIDENCE_KEY_ID,
        private_key=keys[0],
        nonce_byte=83,
        attachments=dict(sealed_target.attachments_by_digest),
    )
    verdict = _evaluate(tmp_path / "eval", values, keys)
    assert FailureCode.A4_THRESHOLD_FAILED in {item.code for item in verdict.failures}


def test_sealed_wrong_workspace_leakage_blocks(tmp_path) -> None:
    _, keys = authority(tmp_path / "keys")
    values = evidence_set(keys)
    threshold = next(item for item in values if _role(item) == "A4_RETRIEVAL_THRESHOLD_POLICY")
    calibration = next(item for item in values if _role(item) == "A4_RETRIEVAL_CALIBRATION_RECEIPT")
    index = next(i for i, item in enumerate(values) if _role(item) == "A4_RETRIEVAL_SEALED_TEST_RECEIPT")
    bad_rows = rows("sealed")
    bad_rows[0]["wrong_workspace_count"] = 1
    payload, attachments = evaluation_material(
        "sealed_test",
        bad_rows,
        __import__("hashlib").sha256(threshold.payload_bytes).hexdigest(),
        calibration_digest=__import__("hashlib").sha256(calibration.payload_bytes).hexdigest(),
    )
    values[index] = envelope(
        role="A4_RETRIEVAL_SEALED_TEST_RECEIPT",
        payload=payload,
        key_id=EVIDENCE_KEY_ID,
        private_key=keys[0],
        nonce_byte=79,
        attachments=attachments,
    )
    verdict = _evaluate(tmp_path / "eval", values, keys)
    codes = {item.code for item in verdict.failures}
    assert FailureCode.A4_SEALED_LEAKAGE in codes
    assert FailureCode.A4_THRESHOLD_FAILED in codes


def test_failure_order_is_deterministic_and_meta_only(tmp_path) -> None:
    _, keys = authority(tmp_path / "keys")
    values = evidence_set(keys)[2:]
    verdict = _evaluate(tmp_path / "eval", values, keys)
    assert verdict.failures == tuple(sorted(set(verdict.failures), key=lambda item: item.sort_key()))
    public = verdict.to_public_dict()
    assert all(set(item) == {"code", "role", "artifact_digest", "field_path"} for item in public["failures"])
