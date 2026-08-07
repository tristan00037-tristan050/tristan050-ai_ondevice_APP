"""Immutable SearchQuality evidence closure for the protected Helper1 verdict."""
from __future__ import annotations

import base64
import hashlib
import json
from pathlib import Path, PurePosixPath
from typing import Any, Mapping

from .contracts import (
    AnswerCaseRecordV2,
    AnswerCitationV2,
    AnswerClaimV2,
    EvaluationAnswerDecision,
    EvaluationVariant,
    RetrievalCaseRecordV2,
    RetrievalDecision,
    RetrievalTraceHitV2,
    canonical_json,
    evaluation_run_subject_v2_from_mapping,
)
from .evaluation import (
    evaluate_quality_v2,
    evaluation_query_v2_from_mapping,
    verify_declared_report_v2,
)
from .measurement import MeasurementError, validate_device_measurement_v2

MANIFEST_NAME = "QUALITY_EVIDENCE_MANIFEST.v1.json"
QUALITY_FILES = frozenset(
    {
        "INPUT/corpus-manifest.json",
        "INPUT/queries.jsonl",
        "INPUT/retrieval-policy.json",
        "INPUT/QUALITY_INPUT_PROVENANCE.v1.json",
        "EVALUATION/evaluation-run-subject.json",
        "EVALUATION/start-tree-verdict.json",
        "EVALUATION/retrieval-cases.jsonl",
        "EVALUATION/answer-cases.jsonl",
        "EVALUATION/ablation-retrieval-cases.jsonl",
        "EVALUATION/ablation-answer-cases.jsonl",
        "EVALUATION/quality-report.json",
        "DEVICE/M3/native-measurement.json",
        "DEVICE/M3/raw-bundle.json",
        "DEVICE/M3/device-receipt.json",
        "DEVICE/M3/observer.bin",
        "DEVICE/M4/native-measurement.json",
        "DEVICE/M4/raw-bundle.json",
        "DEVICE/M4/device-receipt.json",
        "DEVICE/M4/observer.bin",
    }
)
MAX_FILE_BYTES = 128 * 1024 * 1024
MAX_TOTAL_BYTES = 512 * 1024 * 1024
DECODING_POLICY_V1 = {
    "schema_version": "butler.helper1.decoding-policy.v1",
    "max_tokens": 1024,
    "temperature_ppm": 100_000,
    "thinking": False,
    "json_output": True,
}


class QualityEvidenceError(RuntimeError):
    pass


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _object(raw: bytes, code: str) -> dict[str, Any]:
    def unique(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise QualityEvidenceError(code)
            result[key] = value
        return result

    try:
        value = json.loads(
            raw,
            object_pairs_hook=unique,
            parse_constant=lambda _value: (_ for _ in ()).throw(ValueError()),
        )
    except (UnicodeError, ValueError, json.JSONDecodeError) as exc:
        raise QualityEvidenceError(code) from exc
    if type(value) is not dict:
        raise QualityEvidenceError(code)
    return value


def _rows(raw: bytes, code: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line in raw.splitlines():
        rows.append(_object(line, code))
    if not rows:
        raise QualityEvidenceError(code)
    return rows


def _score(bits: object) -> float | None:
    if bits is None:
        return None
    if type(bits) is not str or len(bits) != 16:
        raise QualityEvidenceError("QUALITY_RECORD_INVALID")
    import struct

    try:
        return struct.unpack(">d", bytes.fromhex(bits))[0]
    except (ValueError, struct.error) as exc:
        raise QualityEvidenceError("QUALITY_RECORD_INVALID") from exc


def _retrieval(value: Mapping[str, Any]) -> RetrievalCaseRecordV2:
    hits = value.get("hits")
    if type(hits) is not list or any(type(item) is not dict for item in hits):
        raise QualityEvidenceError("QUALITY_RECORD_INVALID")
    record = RetrievalCaseRecordV2(
        query_id=value["query_id"],
        run_id=value["run_id"],
        evaluation_run_subject_sha256=value["evaluation_run_subject_sha256"],
        policy_sha256=value["policy_sha256"],
        encoder_space_sha256=value["encoder_space_sha256"],
        index_manifest_sha256=value["index_manifest_sha256"],
        started_monotonic_ns=value["started_monotonic_ns"],
        finished_monotonic_ns=value["finished_monotonic_ns"],
        decision=RetrievalDecision(value["decision"]),
        reason_code=value["reason_code"],
        hits=tuple(
            RetrievalTraceHitV2(
                workspace_id=item["workspace_id"],
                generation_id=item["generation_id"],
                source_id=item["source_id"],
                chunk_id=item["chunk_id"],
                content_utf8=item["content_utf8"],
                content_sha256=item["content_sha256"],
                dense_score=_score(item["dense_score_bits"]),
                lexical_score=_score(item["lexical_score_bits"]),
                fused_score=_score(item["fused_score_bits"]),
                dense_rank=item["dense_rank"],
                lexical_rank=item["lexical_rank"],
                fused_rank=item["fused_rank"],
            )
            for item in hits
        ),
    )
    if value.get("record_sha256") != record.to_dict()["record_sha256"]:
        raise QualityEvidenceError("QUALITY_RECORD_INVALID")
    return record


def _answer(value: Mapping[str, Any]) -> AnswerCaseRecordV2:
    claims = value.get("claims")
    citations = value.get("citations")
    if (
        type(claims) is not list
        or type(citations) is not list
        or any(type(item) is not dict for item in (*claims, *citations))
    ):
        raise QualityEvidenceError("QUALITY_RECORD_INVALID")
    record = AnswerCaseRecordV2(
        query_id=value["query_id"],
        run_id=value["run_id"],
        evaluation_run_subject_sha256=value["evaluation_run_subject_sha256"],
        execution_variant=EvaluationVariant(value["execution_variant"]),
        generator_identity_sha256=value["generator_identity_sha256"],
        prompt_template_sha256=value["prompt_template_sha256"],
        decision=EvaluationAnswerDecision(value["decision"]),
        reason_code=value["reason_code"],
        answer_utf8=value["answer_utf8"],
        claims=tuple(AnswerClaimV2(**item) for item in claims),
        citations=tuple(AnswerCitationV2(**item) for item in citations),
        normal_index_manifest_sha256=value["normal_index_manifest_sha256"],
        ablation_index_manifest_sha256=value["ablation_index_manifest_sha256"],
        seed=value["seed"],
        decoding_policy_sha256=value["decoding_policy_sha256"],
        started_monotonic_ns=value["started_monotonic_ns"],
        finished_monotonic_ns=value["finished_monotonic_ns"],
    )
    if value.get("record_sha256") != record.to_dict()["record_sha256"]:
        raise QualityEvidenceError("QUALITY_RECORD_INVALID")
    return record


def load_quality_directory(root: Path) -> dict[str, bytes]:
    """Freeze the exact producer output inventory before packaging."""
    files: dict[str, bytes] = {}
    total = 0
    try:
        paths = sorted(root.rglob("*"))
    except OSError as exc:
        raise QualityEvidenceError("QUALITY_INVENTORY_INVALID") from exc
    for path in paths:
        relative = path.relative_to(root).as_posix()
        pure = PurePosixPath(relative)
        if path.is_symlink() or pure.is_absolute() or ".." in pure.parts:
            raise QualityEvidenceError("QUALITY_INVENTORY_INVALID")
        if path.is_dir():
            continue
        if not path.is_file():
            raise QualityEvidenceError("QUALITY_INVENTORY_INVALID")
        raw = path.read_bytes()
        if not 0 < len(raw) <= MAX_FILE_BYTES:
            raise QualityEvidenceError("QUALITY_INVENTORY_INVALID")
        total += len(raw)
        if total > MAX_TOTAL_BYTES:
            raise QualityEvidenceError("QUALITY_INVENTORY_INVALID")
        files[relative] = raw
    if set(files) != QUALITY_FILES | {MANIFEST_NAME}:
        raise QualityEvidenceError("QUALITY_INVENTORY_INVALID")
    verify_manifest(files)
    return files


def build_manifest(
    files: Mapping[str, bytes],
    *,
    source_commit: str,
    source_tree: str,
    evaluation_run_id: str,
    evaluation_run_attempt: int,
    producer_run_id: str,
    producer_run_attempt: int,
    workflow_id: int,
    workflow_ref: str,
    workflow_sha256: str,
) -> bytes:
    if set(files) != QUALITY_FILES:
        raise QualityEvidenceError("QUALITY_INVENTORY_INVALID")
    manifest = {
        "schema_version": "butler.helper1.quality-evidence-manifest.v1",
        "source_commit": source_commit,
        "source_tree": source_tree,
        "evaluation_run_id": evaluation_run_id,
        "evaluation_run_attempt": evaluation_run_attempt,
        "producer_run_id": producer_run_id,
        "producer_run_attempt": producer_run_attempt,
        "workflow_id": workflow_id,
        "workflow_ref": workflow_ref,
        "workflow_sha256": workflow_sha256,
        "files": {
            name: {"bytes": len(raw), "sha256": _sha(raw)}
            for name, raw in sorted(files.items())
        },
    }
    return canonical_json(manifest) + b"\n"


def verify_manifest(files: Mapping[str, bytes]) -> dict[str, Any]:
    try:
        manifest = _object(files[MANIFEST_NAME], "QUALITY_MANIFEST_INVALID")
    except KeyError as exc:
        raise QualityEvidenceError("QUALITY_MANIFEST_INVALID") from exc
    records = manifest.get("files")
    if (
        set(manifest)
        != {
            "schema_version",
            "source_commit",
            "source_tree",
            "evaluation_run_id",
            "evaluation_run_attempt",
            "producer_run_id",
            "producer_run_attempt",
            "workflow_id",
            "workflow_ref",
            "workflow_sha256",
            "files",
        }
        or manifest.get("schema_version") != "butler.helper1.quality-evidence-manifest.v1"
        or type(records) is not dict
        or set(records) != QUALITY_FILES
        or set(files) != QUALITY_FILES | {MANIFEST_NAME}
    ):
        raise QualityEvidenceError("QUALITY_MANIFEST_INVALID")
    for name in QUALITY_FILES:
        record = records.get(name)
        raw = files[name]
        if (
            type(record) is not dict
            or set(record) != {"bytes", "sha256"}
            or record.get("bytes") != len(raw)
            or record.get("sha256") != _sha(raw)
        ):
            raise QualityEvidenceError("QUALITY_MANIFEST_INVALID")
    if canonical_json(manifest) + b"\n" != files[MANIFEST_NAME]:
        raise QualityEvidenceError("QUALITY_MANIFEST_INVALID")
    return manifest


def verify_quality_evidence(
    files: Mapping[str, bytes],
    *,
    expected_commit: str,
    expected_tree: str,
    expected_producer_run: str,
    expected_producer_run_attempt: int,
    expected_workflow_id: int,
    expected_workflow_ref: str,
    expected_workflow_sha256: str,
    threshold_approval_payload_sha256: str,
    threshold_policy_bytes: bytes,
    threshold_approval_envelope_sha256: str,
    device_trust_policy: Mapping[str, Any],
    now_epoch_s: int,
) -> dict[str, str]:
    """Recompute metrics and both device receipts from package-contained bytes."""
    manifest = verify_manifest(files)
    provenance = _object(
        files["INPUT/QUALITY_INPUT_PROVENANCE.v1.json"],
        "QUALITY_INPUT_PROVENANCE_INVALID",
    )
    if (
        manifest.get("source_commit") != expected_commit
        or manifest.get("source_tree") != expected_tree
        or manifest.get("producer_run_id") != expected_producer_run
        or manifest.get("producer_run_attempt") != expected_producer_run_attempt
        or manifest.get("workflow_id") != expected_workflow_id
        or manifest.get("workflow_ref") != expected_workflow_ref
        or manifest.get("workflow_sha256") != expected_workflow_sha256
        or set(provenance)
        != {
            "schema_version",
            "repository_id",
            "repository_name",
            "subject_commit",
            "subject_tree",
            "producer_workflow_ref",
            "producer_workflow_id",
            "producer_workflow_sha256",
            "run_id",
            "run_attempt",
            "event_name",
            "artifact_id",
            "artifact_name",
            "artifact_sha256",
        }
        or provenance.get("schema_version")
        != "butler.helper1.quality-input-provenance.v1"
        or provenance.get("subject_commit") != expected_commit
        or provenance.get("subject_tree") != expected_tree
        or type(provenance.get("producer_workflow_id")) is not int
        or provenance["producer_workflow_id"] < 1
        or type(provenance.get("run_id")) is not int
        or provenance["run_id"] < 1
        or type(provenance.get("run_attempt")) is not int
        or provenance["run_attempt"] < 1
        or type(provenance.get("artifact_id")) is not int
        or provenance["artifact_id"] < 1
        or type(provenance.get("artifact_sha256")) is not str
        or len(provenance["artifact_sha256"]) != 64
    ):
        raise QualityEvidenceError("QUALITY_SUBJECT_MISMATCH")

    subject = evaluation_run_subject_v2_from_mapping(
        _object(files["EVALUATION/evaluation-run-subject.json"], "QUALITY_SUBJECT_INVALID")
    )
    if (
        subject.source_commit != expected_commit
        or subject.source_tree != expected_tree
        or manifest.get("evaluation_run_id") != f'{provenance["run_id"]}:{provenance["run_attempt"]}'
        or manifest.get("evaluation_run_attempt") != provenance["run_attempt"]
        or subject.run_id != manifest.get("evaluation_run_id")
        or subject.run_attempt != manifest.get("evaluation_run_attempt")
        or subject.threshold_policy_sha256 != threshold_approval_payload_sha256
        or subject.threshold_approval_receipt_sha256 != threshold_approval_envelope_sha256
    ):
        raise QualityEvidenceError("QUALITY_SUBJECT_MISMATCH")
    queries = tuple(
        evaluation_query_v2_from_mapping(row)
        for row in _rows(files["INPUT/queries.jsonl"], "QUALITY_QUERY_INVALID")
    )
    retrieval_rows = tuple(
        _retrieval(row)
        for row in _rows(files["EVALUATION/retrieval-cases.jsonl"], "QUALITY_RECORD_INVALID")
    )
    answer_rows = tuple(
        _answer(row)
        for row in _rows(files["EVALUATION/answer-cases.jsonl"], "QUALITY_RECORD_INVALID")
    )
    ablation_retrieval_rows = tuple(
        _retrieval(row)
        for row in _rows(
            files["EVALUATION/ablation-retrieval-cases.jsonl"], "QUALITY_RECORD_INVALID"
        )
    )
    ablation_answer_rows = tuple(
        _answer(row)
        for row in _rows(
            files["EVALUATION/ablation-answer-cases.jsonl"], "QUALITY_RECORD_INVALID"
        )
    )
    corpus = _object(files["INPUT/corpus-manifest.json"], "QUALITY_CORPUS_INVALID")
    retrieval_policy = _object(files["INPUT/retrieval-policy.json"], "QUALITY_POLICY_INVALID")
    threshold_policy = _object(threshold_policy_bytes, "QUALITY_POLICY_INVALID")
    report = evaluate_quality_v2(
        queries,
        {record.query_id: record for record in retrieval_rows},
        {record.query_id: record for record in answer_rows},
        execution_subject=subject,
        ablation_retrieval_records={record.query_id: record for record in ablation_retrieval_rows},
        ablation_answer_records={record.query_id: record for record in ablation_answer_rows},
        split="sealed_test",
        corpus_manifest_sha256=_sha(canonical_json(corpus)),
        retrieval_policy_sha256=_sha(canonical_json(retrieval_policy)),
        threshold_policy_sha256=_sha(canonical_json(threshold_policy)),
    )
    declared = _object(files["EVALUATION/quality-report.json"], "QUALITY_REPORT_INVALID")
    verify_declared_report_v2(declared, report)
    metrics = report.get("metrics")
    if (
        type(metrics) is not dict
        or report.get("canary_leakage_count") != 0
        or report.get("wrong_workspace_hit_count") != 0
        or report.get("stale_generation_hit_count") != 0
    ):
        raise QualityEvidenceError("QUALITY_THRESHOLD_FAILED")
    minimum = threshold_policy.get("minimum_metrics_ppm")
    maximum = threshold_policy.get("maximum_metrics_ppm")
    required_strata = threshold_policy.get("required_strata")
    strata = report.get("strata_sample_counts")
    issued = threshold_policy.get("issued_at_epoch_s")
    expires = threshold_policy.get("expires_at_epoch_s")
    if (
        threshold_policy.get("schema_version")
        != "butler.helper1.retrieval-threshold-policy.v1"
        or threshold_policy.get("corpus_manifest_sha256") != subject.corpus_manifest_sha256
        or type(minimum) is not dict
        or type(maximum) is not dict
        or type(required_strata) is not list
        or type(strata) is not dict
        or type(issued) is not int
        or type(expires) is not int
        or not issued <= now_epoch_s < expires
        or type(threshold_policy.get("minimum_sample_count")) is not int
        or report["sample_count"] < threshold_policy["minimum_sample_count"]
        or type(threshold_policy.get("minimum_per_stratum_count")) is not int
        or any(
            type(stratum) is not str
            or type(strata.get(stratum)) is not int
            or strata[stratum] < threshold_policy["minimum_per_stratum_count"]
            for stratum in required_strata
        )
        or any(
            type(name) is not str
            or type(limit) is not int
            or type(metrics.get(name)) is not int
            or metrics[name] < limit
            for name, limit in minimum.items()
        )
        or any(
            type(name) is not str
            or type(limit) is not int
            or type(metrics.get(name)) is not int
            or metrics[name] > limit
            for name, limit in maximum.items()
        )
    ):
        raise QualityEvidenceError("QUALITY_THRESHOLD_FAILED")

    if (
        type(device_trust_policy) is not dict
        or device_trust_policy.get("schema_version") != "butler.helper1.device-trust-policy.v1"
        or device_trust_policy.get("enabled") is not True
        or type(device_trust_policy.get("key_id")) is not str
        or type(device_trust_policy.get("public_key_b64")) is not str
        or type(device_trust_policy.get("measurement_policy_sha256")) is not str
    ):
        raise QualityEvidenceError("MEASUREMENT_TRUST_ROOT_UNCONFIGURED")
    try:
        public_key = base64.b64decode(device_trust_policy["public_key_b64"], validate=True)
    except (ValueError, TypeError) as exc:
        raise QualityEvidenceError("MEASUREMENT_TRUST_ROOT_INVALID") from exc
    key_id = str(device_trust_policy["key_id"])
    if _sha(public_key) != key_id:
        raise QualityEvidenceError("MEASUREMENT_TRUST_ROOT_INVALID")
    device_digests: dict[str, str] = {}
    for device in ("M3", "M4"):
        prefix = f"DEVICE/{device}"
        try:
            verified = validate_device_measurement_v2(
                _object(files[f"{prefix}/native-measurement.json"], "DEVICE_MEASUREMENT_INVALID"),
                expected_device_class=device,
                expected_source_commit=expected_commit,
                expected_source_tree=expected_tree,
                expected_run_id=subject.run_id,
                expected_run_attempt=subject.run_attempt,
                raw_bundle=files[f"{prefix}/raw-bundle.json"],
                device_receipt=files[f"{prefix}/device-receipt.json"],
                observer_binary=files[f"{prefix}/observer.bin"],
                public_key_bytes=public_key,
                expected_key_id=key_id,
                expected_policy_sha256=device_trust_policy["measurement_policy_sha256"],
                now_epoch_s=now_epoch_s,
            )
        except (MeasurementError, KeyError, TypeError, ValueError) as exc:
            raise QualityEvidenceError(str(exc) or "DEVICE_MEASUREMENT_INVALID") from exc
        device_digests[device] = _sha(canonical_json(verified))
    return {
        "quality_manifest_sha256": _sha(files[MANIFEST_NAME]),
        "quality_report_sha256": _sha(files["EVALUATION/quality-report.json"]),
        "evaluation_run_subject_sha256": subject.digest,
        "m3_measurement_sha256": device_digests["M3"],
        "m4_measurement_sha256": device_digests["M4"],
    }
