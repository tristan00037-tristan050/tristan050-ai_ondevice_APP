#!/usr/bin/env python3
"""Independently recompute Helper1 v6.1 quality from per-case records."""
from __future__ import annotations

import argparse
import json
import os
import struct
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from butler_pc_core.helper1.contracts import (  # noqa: E402
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
    sha256_bytes,
)
from butler_pc_core.helper1.evaluation import (  # noqa: E402
    evaluate_quality_v2,
    evaluation_query_v2_from_mapping,
)
from butler_pc_core.helper1.failure_codes import Helper1FailureCode, Helper1V61Error  # noqa: E402

MAX_BYTES = 128 * 1024 * 1024


def _rows(path: Path) -> list[dict[str, object]]:
    raw = path.read_bytes()
    if not 0 < len(raw) <= MAX_BYTES:
        raise Helper1V61Error(Helper1FailureCode.EVALUATION_INPUT_UNAVAILABLE)
    rows: list[dict[str, object]] = []
    try:
        for line in raw.splitlines():
            value = json.loads(line, parse_constant=lambda _value: (_ for _ in ()).throw(ValueError()))
            if not isinstance(value, dict):
                raise ValueError
            rows.append(value)
    except (UnicodeError, ValueError, json.JSONDecodeError) as exc:
        raise Helper1V61Error(Helper1FailureCode.EVALUATION_INPUT_UNAVAILABLE) from exc
    if not rows:
        raise Helper1V61Error(Helper1FailureCode.EVALUATION_INPUT_UNAVAILABLE)
    return rows


def _object(path: Path, *, failure: Helper1FailureCode) -> dict[str, object]:
    raw = path.read_bytes()
    if not 0 < len(raw) <= MAX_BYTES:
        raise Helper1V61Error(failure)
    try:
        value = json.loads(
            raw,
            parse_constant=lambda _value: (_ for _ in ()).throw(ValueError()),
        )
    except (UnicodeError, ValueError, json.JSONDecodeError) as exc:
        raise Helper1V61Error(failure) from exc
    if not isinstance(value, dict):
        raise Helper1V61Error(failure)
    return value


def _score(bits: object) -> float | None:
    if bits is None:
        return None
    if not isinstance(bits, str) or len(bits) != 16:
        raise Helper1V61Error(Helper1FailureCode.MEASUREMENT_RECOMPUTE_MISMATCH)
    try:
        return struct.unpack(">d", bytes.fromhex(bits))[0]
    except (ValueError, struct.error) as exc:
        raise Helper1V61Error(Helper1FailureCode.MEASUREMENT_RECOMPUTE_MISMATCH) from exc


def _retrieval(value: dict[str, object]) -> RetrievalCaseRecordV2:
    hits_raw = value.get("hits")
    if not isinstance(hits_raw, list):
        raise Helper1V61Error(Helper1FailureCode.MEASUREMENT_RECOMPUTE_MISMATCH)
    hits = tuple(
        RetrievalTraceHitV2(
            workspace_id=item["workspace_id"], generation_id=item["generation_id"],
            source_id=item["source_id"], chunk_id=item["chunk_id"],
            content_utf8=item["content_utf8"], content_sha256=item["content_sha256"], dense_score=_score(item["dense_score_bits"]),
            lexical_score=_score(item["lexical_score_bits"]), fused_score=_score(item["fused_score_bits"]),
            dense_rank=item["dense_rank"], lexical_rank=item["lexical_rank"], fused_rank=item["fused_rank"],
        )
        for item in hits_raw if isinstance(item, dict)
    )
    if len(hits) != len(hits_raw):
        raise Helper1V61Error(Helper1FailureCode.MEASUREMENT_RECOMPUTE_MISMATCH)
    record = RetrievalCaseRecordV2(
        query_id=value["query_id"], run_id=value["run_id"],
        evaluation_run_subject_sha256=value["evaluation_run_subject_sha256"], policy_sha256=value["policy_sha256"],
        encoder_space_sha256=value["encoder_space_sha256"], index_manifest_sha256=value["index_manifest_sha256"],
        started_monotonic_ns=value["started_monotonic_ns"], finished_monotonic_ns=value["finished_monotonic_ns"],
        decision=RetrievalDecision(value["decision"]), reason_code=value["reason_code"], hits=hits,
    )
    if value.get("record_sha256") != record.to_dict()["record_sha256"]:
        raise Helper1V61Error(Helper1FailureCode.MEASUREMENT_RECOMPUTE_MISMATCH)
    return record


def _answer(value: dict[str, object]) -> AnswerCaseRecordV2:
    claims_raw = value.get("claims")
    citations_raw = value.get("citations")
    if not isinstance(claims_raw, list) or not isinstance(citations_raw, list):
        raise Helper1V61Error(Helper1FailureCode.MEASUREMENT_RECOMPUTE_MISMATCH)
    record = AnswerCaseRecordV2(
        query_id=value["query_id"], run_id=value["run_id"],
        evaluation_run_subject_sha256=value["evaluation_run_subject_sha256"],
        execution_variant=EvaluationVariant(value["execution_variant"]),
        generator_identity_sha256=value["generator_identity_sha256"], prompt_template_sha256=value["prompt_template_sha256"],
        decision=EvaluationAnswerDecision(value["decision"]), reason_code=value["reason_code"], answer_utf8=value["answer_utf8"],
        claims=tuple(AnswerClaimV2(**item) for item in claims_raw if isinstance(item, dict)),
        citations=tuple(AnswerCitationV2(**item) for item in citations_raw if isinstance(item, dict)),
        normal_index_manifest_sha256=value["normal_index_manifest_sha256"],
        ablation_index_manifest_sha256=value["ablation_index_manifest_sha256"], seed=value["seed"],
        decoding_policy_sha256=value["decoding_policy_sha256"], started_monotonic_ns=value["started_monotonic_ns"],
        finished_monotonic_ns=value["finished_monotonic_ns"],
    )
    if value.get("record_sha256") != record.to_dict()["record_sha256"]:
        raise Helper1V61Error(Helper1FailureCode.MEASUREMENT_RECOMPUTE_MISMATCH)
    return record


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--queries", required=True, type=Path)
    parser.add_argument("--retrieval-cases", required=True, type=Path)
    parser.add_argument("--answer-cases", required=True, type=Path)
    parser.add_argument("--ablation-retrieval-cases", type=Path)
    parser.add_argument("--ablation-answer-cases", type=Path)
    parser.add_argument("--execution-subject", required=True, type=Path)
    parser.add_argument("--corpus-manifest", required=True, type=Path)
    parser.add_argument("--retrieval-policy", required=True, type=Path)
    parser.add_argument("--threshold-policy", required=True, type=Path)
    parser.add_argument("--split", default="sealed_test")
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    try:
        queries = tuple(evaluation_query_v2_from_mapping(row) for row in _rows(args.queries))
        retrieval_records = tuple(_retrieval(row) for row in _rows(args.retrieval_cases))
        answer_records = tuple(_answer(row) for row in _rows(args.answer_cases))
        subject = evaluation_run_subject_v2_from_mapping(
            _object(args.execution_subject, failure=Helper1FailureCode.MEASUREMENT_RECOMPUTE_MISMATCH)
        )
        retrieval = {record.query_id: record for record in retrieval_records}
        answers = {record.query_id: record for record in answer_records}
        if len(retrieval) != len(retrieval_records) or len(answers) != len(answer_records):
            raise Helper1V61Error(Helper1FailureCode.MEASUREMENT_RECOMPUTE_MISMATCH)
        if (args.ablation_retrieval_cases is None) != (args.ablation_answer_cases is None):
            raise Helper1V61Error(Helper1FailureCode.RETRIEVAL_DEPENDENCE_NOT_PROVEN)
        ablation_retrieval_records = (
            () if args.ablation_retrieval_cases is None else tuple(
                _retrieval(row) for row in _rows(args.ablation_retrieval_cases)
            )
        )
        ablation_answer_records = (
            () if args.ablation_answer_cases is None else tuple(
                _answer(row) for row in _rows(args.ablation_answer_cases)
            )
        )
        ablation_retrieval = {record.query_id: record for record in ablation_retrieval_records}
        ablation_answers = {record.query_id: record for record in ablation_answer_records}
        if (
            len(ablation_retrieval) != len(ablation_retrieval_records)
            or len(ablation_answers) != len(ablation_answer_records)
        ):
            raise Helper1V61Error(Helper1FailureCode.MEASUREMENT_RECOMPUTE_MISMATCH)
        retrieval_policy = _object(
            args.retrieval_policy,
            failure=Helper1FailureCode.THRESHOLD_POLICY_UNAPPROVED,
        )
        if (
            retrieval_policy.get("schema_version") != "butler.helper1.retrieval-policy.v1"
            or retrieval_policy.get("calibration_state") != "APPROVED"
        ):
            raise Helper1V61Error(Helper1FailureCode.THRESHOLD_POLICY_UNAPPROVED)
        retrieval_policy_sha256 = sha256_bytes(canonical_json(retrieval_policy))
        policy = _object(
            args.threshold_policy,
            failure=Helper1FailureCode.THRESHOLD_POLICY_UNAPPROVED,
        )
        if (
            policy.get("schema_version") != "butler.helper1.retrieval-threshold-policy.v1"
        ):
            raise Helper1V61Error(Helper1FailureCode.THRESHOLD_POLICY_UNAPPROVED)
        policy_sha256 = sha256_bytes(canonical_json(policy))
        corpus = _object(
            args.corpus_manifest,
            failure=Helper1FailureCode.EVALUATION_INPUT_UNAVAILABLE,
        )
        corpus_sha256 = sha256_bytes(canonical_json(corpus))
        report = evaluate_quality_v2(
            queries,
            retrieval,
            answers,
            execution_subject=subject,
            ablation_retrieval_records=ablation_retrieval or None,
            ablation_answer_records=ablation_answers or None,
            split=args.split,
            corpus_manifest_sha256=corpus_sha256,
            retrieval_policy_sha256=retrieval_policy_sha256,
            threshold_policy_sha256=policy_sha256,
        )
        args.output.parent.mkdir(parents=True, exist_ok=True)
        descriptor = os.open(args.output, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        try:
            with os.fdopen(descriptor, "wb", closefd=False) as handle:
                handle.write(canonical_json(report) + b"\n")
                handle.flush()
                os.fsync(handle.fileno())
        finally:
            os.close(descriptor)
    except (Helper1V61Error, OSError, KeyError, TypeError, ValueError) as exc:
        code = exc.code.value if isinstance(exc, Helper1V61Error) else "MEASUREMENT_RECOMPUTE_MISMATCH"
        print("HELPER1_RECOMPUTE_QUALITY_OK=0")
        print(f"ERROR_CODE={code}")
        return 1
    print("HELPER1_RECOMPUTE_QUALITY_OK=1")
    print("ERROR_CODE=NONE")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
