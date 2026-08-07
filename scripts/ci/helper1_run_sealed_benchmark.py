#!/usr/bin/env python3
"""Run sealed Helper1 cases through the canonical native product assemblies."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time
from pathlib import Path
from typing import Sequence

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from butler_pc_core.helper1.composition import (  # noqa: E402
    NativeProductAssembly,
    load_native_ablation_assembly,
    load_native_product_assembly,
)
from butler_pc_core.helper1.contracts import (  # noqa: E402
    AnswerCaseRecordV2,
    AnswerCitationV2,
    AnswerClaimV2,
    EvaluationAnswerDecision,
    EvaluationRunSubjectV2,
    EvaluationVariant,
    RetrievalCaseRecordV2,
    RetrievalDecision,
    canonical_json,
    evaluation_run_subject_v2_from_mapping,
    sha256_bytes,
)
from butler_pc_core.helper1.evaluation import (  # noqa: E402
    EvaluationQueryV2,
    evaluation_query_manifest_sha256,
    evaluation_query_v2_from_mapping,
    validate_partition_v2,
)
from butler_pc_core.helper1.failure_codes import Helper1FailureCode, Helper1V61Error  # noqa: E402
from butler_pc_core.helper1.pipeline import bind_citations, gate_grounding, render_rag_prompt  # noqa: E402
from butler_pc_core.helper1.quality_evidence import DECODING_POLICY_V1  # noqa: E402

MAX_INPUT_BYTES = 128 * 1024 * 1024


def _read(path: Path) -> bytes:
    raw = path.read_bytes()
    if not 0 < len(raw) <= MAX_INPUT_BYTES:
        raise Helper1V61Error(Helper1FailureCode.EVALUATION_INPUT_UNAVAILABLE)
    return raw


def _load_json(raw: bytes) -> dict[str, object]:
    try:
        value = json.loads(raw, parse_constant=lambda _value: (_ for _ in ()).throw(ValueError()))
    except (UnicodeError, ValueError, json.JSONDecodeError) as exc:
        raise Helper1V61Error(Helper1FailureCode.EVALUATION_INPUT_UNAVAILABLE) from exc
    if not isinstance(value, dict):
        raise Helper1V61Error(Helper1FailureCode.EVALUATION_INPUT_UNAVAILABLE)
    return value


def _load_queries(raw: bytes) -> tuple[EvaluationQueryV2, ...]:
    records: list[EvaluationQueryV2] = []
    try:
        for line in raw.splitlines():
            value = json.loads(line, parse_constant=lambda _value: (_ for _ in ()).throw(ValueError()))
            if not isinstance(value, dict):
                raise ValueError
            records.append(evaluation_query_v2_from_mapping(value))
    except (UnicodeError, ValueError, json.JSONDecodeError) as exc:
        raise Helper1V61Error(Helper1FailureCode.EVALUATION_INPUT_UNAVAILABLE) from exc
    if not records:
        raise Helper1V61Error(Helper1FailureCode.EVALUATION_INPUT_UNAVAILABLE)
    return tuple(records)


def _write_jsonl(path: Path, rows: list[dict[str, object]]) -> None:
    raw = b"".join(canonical_json(row) + b"\n" for row in sorted(rows, key=lambda item: str(item["query_id"])))
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(descriptor, "wb", closefd=False) as handle:
            handle.write(raw)
            handle.flush()
            os.fsync(handle.fileno())
    finally:
        os.close(descriptor)


def _assert_assembly_identity(
    assembly: NativeProductAssembly,
    subject: EvaluationRunSubjectV2,
    *,
    expected_index: str,
    policy: dict[str, object],
    prompt_digest: str,
) -> None:
    pipeline = assembly.pipeline
    if not pipeline.retriever.policy.is_calibrated or pipeline.retriever.policy.to_dict() != policy:
        raise Helper1V61Error(Helper1FailureCode.THRESHOLD_POLICY_UNAPPROVED)
    if (
        pipeline.retriever.policy.digest != subject.retrieval_policy_sha256
        or pipeline.embedder.identity.digest != subject.encoder_space_sha256
        or pipeline.index.manifest.digest != expected_index
        or pipeline.generator.identity_sha256 != subject.generator_identity_sha256
        or prompt_digest != subject.prompt_template_sha256
    ):
        raise Helper1V61Error(Helper1FailureCode.EVALUATION_INPUT_UNAVAILABLE)


def _execute_cases(
    assembly: NativeProductAssembly,
    queries: Sequence[EvaluationQueryV2],
    subject: EvaluationRunSubjectV2,
    *,
    variant: EvaluationVariant,
) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    pipeline = assembly.pipeline
    retrieval_rows: list[dict[str, object]] = []
    answer_rows: list[dict[str, object]] = []
    for query in queries:
        started = time.monotonic_ns()
        chunks, trace_hits = pipeline.retriever.search_with_trace(
            query=query.query_utf8,
            index=pipeline.index,
            embedder=pipeline.embedder,
            top_k=10,
            expected_workspace_id=query.workspace_id,
            expected_generation_id=query.generation_id,
        )
        retrieval = RetrievalCaseRecordV2(
            query_id=query.query_id,
            run_id=subject.run_id,
            evaluation_run_subject_sha256=subject.digest,
            policy_sha256=pipeline.retriever.policy.digest,
            encoder_space_sha256=pipeline.embedder.identity.digest,
            index_manifest_sha256=pipeline.index.manifest.digest,
            started_monotonic_ns=started,
            finished_monotonic_ns=time.monotonic_ns(),
            decision=RetrievalDecision.RETRIEVE if chunks else RetrievalDecision.ABSTAIN,
            reason_code=None if chunks else "NO_RELEVANT_EVIDENCE",
            hits=trace_hits,
        )
        retrieval_rows.append(retrieval.to_dict())
        generation_started = time.monotonic_ns()
        reason = gate_grounding(chunks, pipeline.grounding_policy)
        common = {
            "query_id": query.query_id,
            "run_id": subject.run_id,
            "evaluation_run_subject_sha256": subject.digest,
            "execution_variant": variant,
            "generator_identity_sha256": pipeline.generator.identity_sha256,
            "prompt_template_sha256": subject.prompt_template_sha256,
            "normal_index_manifest_sha256": subject.normal_index_manifest_sha256,
            "ablation_index_manifest_sha256": (
                None
                if variant is EvaluationVariant.NORMAL
                else subject.ablation_index_manifest_sha256
            ),
            "seed": subject.seed,
            "decoding_policy_sha256": subject.decoding_policy_sha256,
            "started_monotonic_ns": generation_started,
        }
        if reason is not None:
            answer = AnswerCaseRecordV2(
                **common,
                decision=EvaluationAnswerDecision.ABSTAIN,
                reason_code=reason,
                answer_utf8=None,
                claims=(),
                citations=(),
                finished_monotonic_ns=time.monotonic_ns(),
            )
        else:
            draft = pipeline.generator.generate(render_rag_prompt(query.query_utf8, chunks))
            citations, _ratio = bind_citations(draft, chunks)
            answer_bytes = draft.answer.encode("utf-8")
            cursor = 0
            claims: list[AnswerClaimV2] = []
            for claim in draft.claims:
                claim_bytes = claim.text.encode("utf-8")
                start = answer_bytes.find(claim_bytes, cursor)
                if start < 0:
                    raise Helper1V61Error(Helper1FailureCode.GROUNDING_BELOW_THRESHOLD)
                cursor = start + len(claim_bytes)
                claims.append(AnswerClaimV2(claim.claim_id, sha256_bytes(claim_bytes), start, cursor))
            answer = AnswerCaseRecordV2(
                **common,
                decision=EvaluationAnswerDecision.ANSWER,
                reason_code=None,
                answer_utf8=draft.answer,
                claims=tuple(claims),
                citations=tuple(
                    AnswerCitationV2(
                        citation.claim_id,
                        citation.source_id,
                        citation.chunk_id,
                        citation.evidence_start,
                        citation.evidence_end,
                        citation.evidence_sha256,
                    )
                    for citation in citations
                ),
                finished_monotonic_ns=time.monotonic_ns(),
            )
        answer_rows.append(answer.to_dict())
    return retrieval_rows, answer_rows


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--corpus-artifact", required=True, type=Path)
    parser.add_argument("--answer-key-artifact", required=True, type=Path)
    parser.add_argument("--policy", required=True, type=Path)
    parser.add_argument("--execution-subject", required=True, type=Path)
    parser.add_argument("--source-commit", required=True)
    parser.add_argument("--source-tree", required=True)
    parser.add_argument("--run-attempt", required=True, type=int)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    try:
        corpus_raw = _read(args.corpus_artifact)
        answer_key_raw = _read(args.answer_key_artifact)
        policy_raw = _read(args.policy)
        corpus = _load_json(corpus_raw)
        policy = _load_json(policy_raw)
        subject = evaluation_run_subject_v2_from_mapping(_load_json(_read(args.execution_subject)))
        if corpus.get("schema_version") != "butler.helper1.retrieval-benchmark-manifest.v2":
            raise Helper1V61Error(Helper1FailureCode.EVALUATION_INPUT_UNAVAILABLE)
        if policy.get("schema_version") != "butler.helper1.retrieval-policy.v1" or policy.get("calibration_state") != "APPROVED":
            raise Helper1V61Error(Helper1FailureCode.THRESHOLD_POLICY_UNAPPROVED)
        queries = _load_queries(answer_key_raw)
        policy_digest = sha256_bytes(canonical_json(policy))
        corpus_digest = sha256_bytes(canonical_json(corpus))
        if (
            corpus.get("answer_key_artifact_sha256") != hashlib.sha256(answer_key_raw).hexdigest()
            or subject.query_manifest_sha256 != evaluation_query_manifest_sha256(queries)
            or subject.corpus_manifest_sha256 != corpus_digest
            or subject.retrieval_policy_sha256 != policy_digest
            or subject.decoding_policy_sha256
            != sha256_bytes(canonical_json(DECODING_POLICY_V1))
            or subject.source_commit != args.source_commit
            or subject.source_tree != args.source_tree
            or subject.run_attempt != args.run_attempt
            or subject.run_id != corpus.get("run_id")
        ):
            raise Helper1V61Error(Helper1FailureCode.EVALUATION_INPUT_UNAVAILABLE)
        validate_partition_v2(
            queries,
            sealed_manifest_sha256=corpus["partition_inventory_sha256"],
            tuning_history_manifest_sha256=tuple(corpus.get("tuning_history_manifest_sha256", [])),
        )
        normal = load_native_product_assembly()
        if normal is None:
            raise Helper1V61Error(Helper1FailureCode.ENCODER_ASSET_CLOSURE_INVALID)
        prompt_digest = sha256_bytes(render_rag_prompt.__code__.co_code)
        _assert_assembly_identity(
            normal,
            subject,
            expected_index=subject.normal_index_manifest_sha256,
            policy=policy,
            prompt_digest=prompt_digest,
        )
        if (
            corpus.get("workspace_id") != normal.workspace_id
            or corpus.get("generation_id") != normal.pipeline.index.manifest.generation_id
            or corpus.get("index_manifest_sha256") != subject.normal_index_manifest_sha256
        ):
            raise Helper1V61Error(Helper1FailureCode.WRONG_WORKSPACE_LEAKAGE)

        retrieval_rows, answer_rows = _execute_cases(
            normal, queries, subject, variant=EvaluationVariant.NORMAL
        )
        canaries = tuple(query for query in queries if query.track == "canary_ablation")
        ablation_retrieval_rows: list[dict[str, object]] = []
        ablation_answer_rows: list[dict[str, object]] = []
        if canaries:
            if subject.ablation_index_manifest_sha256 is None:
                raise Helper1V61Error(Helper1FailureCode.RETRIEVAL_DEPENDENCE_NOT_PROVEN)
            ablation = load_native_ablation_assembly(subject.normal_index_manifest_sha256)
            if ablation is None:
                raise Helper1V61Error(Helper1FailureCode.RETRIEVAL_DEPENDENCE_NOT_PROVEN)
            _assert_assembly_identity(
                ablation,
                subject,
                expected_index=subject.ablation_index_manifest_sha256,
                policy=policy,
                prompt_digest=prompt_digest,
            )
            if (
                ablation.workspace_id != normal.workspace_id
                or ablation.pipeline.index.manifest.generation_id
                != normal.pipeline.index.manifest.generation_id
            ):
                raise Helper1V61Error(Helper1FailureCode.RETRIEVAL_DEPENDENCE_NOT_PROVEN)
            ablation_retrieval_rows, ablation_answer_rows = _execute_cases(
                ablation, canaries, subject, variant=EvaluationVariant.ABLATION
            )
        elif subject.ablation_index_manifest_sha256 is not None:
            raise Helper1V61Error(Helper1FailureCode.RETRIEVAL_DEPENDENCE_NOT_PROVEN)

        args.output.mkdir(parents=True, mode=0o700)
        _write_jsonl(args.output / "retrieval-cases.jsonl", retrieval_rows)
        _write_jsonl(args.output / "answer-cases.jsonl", answer_rows)
        if canaries:
            _write_jsonl(args.output / "ablation-retrieval-cases.jsonl", ablation_retrieval_rows)
            _write_jsonl(args.output / "ablation-answer-cases.jsonl", ablation_answer_rows)
        subject_path = args.output / "evaluation-run-subject.json"
        subject_path.write_bytes(canonical_json(subject.to_dict()) + b"\n")
    except (Helper1V61Error, OSError, KeyError, TypeError, ValueError) as exc:
        code = exc.code.value if isinstance(exc, Helper1V61Error) else "EVALUATION_INPUT_UNAVAILABLE"
        print("HELPER1_SEALED_BENCHMARK_OK=0")
        print(f"ERROR_CODE={code}")
        return 1
    print("HELPER1_SEALED_BENCHMARK_OK=1")
    print("ERROR_CODE=NONE")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
