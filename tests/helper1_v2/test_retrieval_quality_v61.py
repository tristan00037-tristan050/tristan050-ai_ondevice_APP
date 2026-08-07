from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import uuid
from dataclasses import asdict, replace
from pathlib import Path

import pytest

from butler_pc_core.helper1.contracts import (
    AnswerCaseRecordV2,
    AnswerCitationV2,
    AnswerClaimV2,
    EvaluationAnswerDecision,
    EvaluationRunSubjectV2,
    EvaluationVariant,
    RetrievalCaseRecordV2,
    RetrievalDecision,
    RetrievalTraceHitV2,
    float64_bits,
)
from butler_pc_core.helper1.evaluation import (
    AllowedEvidenceV2,
    ClaimEvidenceBindingV2,
    EvaluationQueryV2,
    RelevantEvidenceV2,
    RetrievalEvaluationError,
    evaluate_quality_v2,
    evaluation_query_v2_from_mapping,
    evaluation_query_manifest_sha256,
    ppm,
    validate_partition_v2,
    verify_declared_report_v2,
)
from butler_pc_core.helper1.failure_codes import Helper1FailureCode, Helper1V61Error

DIGEST = "a" * 64
WORKSPACE = str(uuid.uuid4())
GENERATION = str(uuid.uuid4())
ROOT = Path(__file__).resolve().parents[2]


def _query(query_id: str, *, answerable: bool, group: str, split: str = "sealed_test") -> EvaluationQueryV2:
    text = f"query {query_id}"
    relevant = (
        RelevantEvidenceV2("source", "chunk", hashlib.sha256(b"evidence").hexdigest()),
    ) if answerable else ()
    return EvaluationQueryV2(
        query_id=query_id,
        group_id=group,
        paraphrase_cluster_id=f"p-{group}",
        source_family_id=f"s-{group}",
        split=split,
        track="private_retrieval" if answerable else "unanswerable",
        query_utf8=text,
        query_sha256=hashlib.sha256(text.encode()).hexdigest(),
        workspace_id=WORKSPACE,
        generation_id=GENERATION,
        answerable=answerable,
        language="ko",
        document_type="contract",
        difficulty="normal",
        robustness_tags=(),
        relevant=relevant,
        required_claim_evidence_bindings=(
            (
                ClaimEvidenceBindingV2(
                    fact_sha256=hashlib.sha256(b"claim").hexdigest(),
                    allowed_evidence=(
                        AllowedEvidenceV2(
                            "source", "chunk", hashlib.sha256(b"evidence").hexdigest()
                        ),
                    ),
                ),
            )
            if answerable
            else ()
        ),
    )


def _subject(
    queries: tuple[EvaluationQueryV2, ...],
    *,
    corpus: str = DIGEST,
    retrieval_policy: str = DIGEST,
    threshold_policy: str = DIGEST,
) -> EvaluationRunSubjectV2:
    return EvaluationRunSubjectV2(
        run_id="run-1",
        run_attempt=1,
        source_commit="1" * 40,
        source_tree="2" * 40,
        query_manifest_sha256=evaluation_query_manifest_sha256(queries),
        corpus_manifest_sha256=corpus,
        retrieval_policy_sha256=retrieval_policy,
        threshold_policy_sha256=threshold_policy,
        threshold_approval_receipt_sha256="e" * 64,
        encoder_space_sha256="b" * 64,
        normal_index_manifest_sha256="c" * 64,
        ablation_index_manifest_sha256=None,
        generator_identity_sha256=DIGEST,
        prompt_template_sha256="b" * 64,
        decoding_policy_sha256="d" * 64,
        seed=0,
    )


def _retrieval(query_id: str, *, answerable: bool, subject: EvaluationRunSubjectV2) -> RetrievalCaseRecordV2:
    hits = (
        RetrievalTraceHitV2(
            workspace_id=WORKSPACE,
            generation_id=GENERATION,
            source_id="source",
            chunk_id="chunk",
            content_utf8="evidence",
            content_sha256=hashlib.sha256(b"evidence").hexdigest(),
            dense_score=0.8,
            lexical_score=0.5,
            fused_score=0.03,
            dense_rank=1,
            lexical_rank=1,
            fused_rank=1,
        ),
    ) if answerable else ()
    return RetrievalCaseRecordV2(
        query_id=query_id,
        run_id="run-1",
        evaluation_run_subject_sha256=subject.digest,
        policy_sha256=subject.retrieval_policy_sha256,
        encoder_space_sha256=subject.encoder_space_sha256,
        index_manifest_sha256=subject.normal_index_manifest_sha256,
        started_monotonic_ns=1,
        finished_monotonic_ns=2,
        decision=RetrievalDecision.RETRIEVE if answerable else RetrievalDecision.ABSTAIN,
        reason_code=None if answerable else "NO_RELEVANT_EVIDENCE",
        hits=hits,
    )


def _abstain(query_id: str, *, subject: EvaluationRunSubjectV2) -> AnswerCaseRecordV2:
    return AnswerCaseRecordV2(
        query_id=query_id,
        run_id="run-1",
        evaluation_run_subject_sha256=subject.digest,
        execution_variant=EvaluationVariant.NORMAL,
        generator_identity_sha256=subject.generator_identity_sha256,
        prompt_template_sha256=subject.prompt_template_sha256,
        decision=EvaluationAnswerDecision.ABSTAIN,
        reason_code="NO_RELEVANT_EVIDENCE",
        answer_utf8=None,
        claims=(),
        citations=(),
        normal_index_manifest_sha256=subject.normal_index_manifest_sha256,
        ablation_index_manifest_sha256=None,
        seed=0,
        decoding_policy_sha256=subject.decoding_policy_sha256,
        started_monotonic_ns=2,
        finished_monotonic_ns=3,
    )


def _answer(query_id: str, *, subject: EvaluationRunSubjectV2, source: str = "source", chunk: str = "chunk") -> AnswerCaseRecordV2:
    answer = "claim"
    return AnswerCaseRecordV2(
        query_id=query_id,
        run_id=subject.run_id,
        evaluation_run_subject_sha256=subject.digest,
        execution_variant=EvaluationVariant.NORMAL,
        generator_identity_sha256=subject.generator_identity_sha256,
        prompt_template_sha256=subject.prompt_template_sha256,
        decision=EvaluationAnswerDecision.ANSWER,
        reason_code=None,
        answer_utf8=answer,
        claims=(AnswerClaimV2("claim-1", hashlib.sha256(answer.encode()).hexdigest(), 0, len(answer)),),
        citations=(AnswerCitationV2("claim-1", source, chunk, 0, 8, hashlib.sha256(b"evidence").hexdigest()),),
        normal_index_manifest_sha256=subject.normal_index_manifest_sha256,
        ablation_index_manifest_sha256=None,
        seed=subject.seed,
        decoding_policy_sha256=subject.decoding_policy_sha256,
        started_monotonic_ns=2,
        finished_monotonic_ns=3,
    )


def test_false_abstention_is_not_removed_from_denominator() -> None:
    queries = (_query("q1", answerable=True, group="g1"), _query("q2", answerable=False, group="g2"))
    subject = _subject(queries)
    report = evaluate_quality_v2(
        queries,
        {query.query_id: _retrieval(query.query_id, answerable=query.answerable, subject=subject) for query in queries},
        {query.query_id: _abstain(query.query_id, subject=subject) for query in queries},
        execution_subject=subject,
        split="sealed_test",
        corpus_manifest_sha256=DIGEST,
        retrieval_policy_sha256=DIGEST,
        threshold_policy_sha256=DIGEST,
    )
    assert report["metrics"]["abstention_precision"]["ppm"] == 500_000
    assert report["metrics"]["false_abstention_rate"]["ppm"] == 1_000_000
    assert report["metrics"]["recall_at_1_ppm"] == 1_000_000
    assert report["answerable_count"] == 1


def test_ppm_half_up_and_declared_report_mutation() -> None:
    assert ppm(1, 2) == 500_000
    assert ppm(1, 3) == 333_333
    verify_declared_report_v2({"a": 1}, {"a": 1})
    with pytest.raises(Helper1V61Error) as caught:
        verify_declared_report_v2({"a": 2}, {"a": 1})
    assert caught.value.code is Helper1FailureCode.MEASUREMENT_RECOMPUTE_MISMATCH


def test_partition_group_source_and_tuning_leakage() -> None:
    sealed = _query("q1", answerable=True, group="shared")
    calibration = _query("q2", answerable=True, group="shared", split="calibration")
    with pytest.raises(Helper1V61Error) as group_error:
        validate_partition_v2((sealed, calibration), sealed_manifest_sha256=DIGEST, tuning_history_manifest_sha256=())
    assert group_error.value.code is Helper1FailureCode.EVALUATION_GROUP_LEAKAGE
    with pytest.raises(Helper1V61Error) as tuning_error:
        validate_partition_v2((sealed,), sealed_manifest_sha256=DIGEST, tuning_history_manifest_sha256=(DIGEST,))
    assert tuning_error.value.code is Helper1FailureCode.SEALED_TEST_REUSED_AFTER_TUNING


def test_binary64_trace_rejects_negative_zero() -> None:
    with pytest.raises(ValueError):
        float64_bits(-0.0, "SCORE_INVALID")


def test_wrong_content_is_not_relevant_and_mixed_subject_is_rejected() -> None:
    queries = (_query("q1", answerable=True, group="g1"),)
    subject = _subject(queries)
    wrong = RetrievalTraceHitV2(
        workspace_id=WORKSPACE,
        generation_id=GENERATION,
        source_id="source",
        chunk_id="chunk",
        content_utf8="attacker",
        content_sha256=hashlib.sha256(b"attacker").hexdigest(),
        dense_score=0.8,
        lexical_score=0.5,
        fused_score=0.03,
        dense_rank=1,
        lexical_rank=1,
        fused_rank=1,
    )
    record = RetrievalCaseRecordV2(
        query_id="q1",
        run_id=subject.run_id,
        evaluation_run_subject_sha256=subject.digest,
        policy_sha256=subject.retrieval_policy_sha256,
        encoder_space_sha256=subject.encoder_space_sha256,
        index_manifest_sha256=subject.normal_index_manifest_sha256,
        started_monotonic_ns=1,
        finished_monotonic_ns=2,
        decision=RetrievalDecision.RETRIEVE,
        reason_code=None,
        hits=(wrong,),
    )
    report = evaluate_quality_v2(
        queries,
        {"q1": record},
        {"q1": _abstain("q1", subject=subject)},
        execution_subject=subject,
        split="sealed_test",
        corpus_manifest_sha256=DIGEST,
        retrieval_policy_sha256=DIGEST,
        threshold_policy_sha256=DIGEST,
    )
    assert report["metrics"]["recall_at_1_ppm"] == 0

    mixed = EvaluationRunSubjectV2(**{**subject.to_dict(), "run_id": "other-run"})
    with pytest.raises(Exception, match="EVALUATION_SUBJECT_MISMATCH"):
        evaluate_quality_v2(
            queries,
            {"q1": record},
            {"q1": _abstain("q1", subject=subject)},
            execution_subject=mixed,
            split="sealed_test",
            corpus_manifest_sha256=DIGEST,
            retrieval_policy_sha256=DIGEST,
            threshold_policy_sha256=DIGEST,
        )


def test_citation_must_reference_retrieved_bytes() -> None:
    queries = (_query("q1", answerable=True, group="g1"),)
    subject = _subject(queries)
    with pytest.raises(Exception, match="EVALUATION_CITATION_NOT_RETRIEVED"):
        evaluate_quality_v2(
            queries,
            {"q1": _retrieval("q1", answerable=True, subject=subject)},
            {"q1": _answer("q1", subject=subject, source="other", chunk="other")},
            execution_subject=subject,
            split="sealed_test",
            corpus_manifest_sha256=DIGEST,
            retrieval_policy_sha256=DIGEST,
            threshold_policy_sha256=DIGEST,
        )


def test_valid_citation_to_unrelated_evidence_does_not_ground_false_claim() -> None:
    query = replace(
        _query("q1", answerable=True, group="g1"),
        required_claim_evidence_bindings=(
            ClaimEvidenceBindingV2(
                fact_sha256=hashlib.sha256(b"expected fact").hexdigest(),
                allowed_evidence=(
                    AllowedEvidenceV2(
                        "source", "chunk", hashlib.sha256(b"evidence").hexdigest()
                    ),
                ),
            ),
        ),
    )
    subject = _subject((query,))
    report = evaluate_quality_v2(
        (query,),
        {query.query_id: _retrieval(query.query_id, answerable=True, subject=subject)},
        {query.query_id: _answer(query.query_id, subject=subject)},
        execution_subject=subject,
        split="sealed_test",
        corpus_manifest_sha256=DIGEST,
        retrieval_policy_sha256=DIGEST,
        threshold_policy_sha256=DIGEST,
    )
    assert report["metrics"]["evidence_span_validity_ppm"] == 1_000_000
    assert report["metrics"]["claim_grounding_precision"]["ppm"] == 0


def test_query_answer_key_round_trip_requires_claim_evidence_bindings() -> None:
    query = _query("q1", answerable=True, group="g1")
    assert evaluation_query_v2_from_mapping(query.to_dict()) == query

    legacy = query.to_dict()
    legacy["required_fact_sha256"] = [hashlib.sha256(b"claim").hexdigest()]
    del legacy["required_claim_evidence_bindings"]
    with pytest.raises(RetrievalEvaluationError, match="EVALUATION_QUERY_SCHEMA_INVALID"):
        evaluation_query_v2_from_mapping(legacy)


def test_crossed_valid_claim_evidence_pairs_do_not_ground() -> None:
    facts = ("fact alpha", "fact beta")
    evidence = ("evidence alpha", "evidence beta")
    base = _query("q1", answerable=True, group="g1")
    relevant = tuple(
        RelevantEvidenceV2(
            "source", f"chunk-{index}", hashlib.sha256(raw.encode()).hexdigest()
        )
        for index, raw in enumerate(evidence, start=1)
    )
    query = replace(
        base,
        relevant=relevant,
        required_claim_evidence_bindings=tuple(
            ClaimEvidenceBindingV2(
                fact_sha256=hashlib.sha256(fact.encode()).hexdigest(),
                allowed_evidence=(
                    AllowedEvidenceV2(item.source_id, item.chunk_id, item.evidence_sha256),
                ),
            )
            for fact, item in zip(facts, relevant, strict=True)
        ),
    )
    subject = _subject((query,))
    hits = tuple(
        RetrievalTraceHitV2(
            workspace_id=WORKSPACE,
            generation_id=GENERATION,
            source_id=item.source_id,
            chunk_id=item.chunk_id,
            content_utf8=raw,
            content_sha256=item.evidence_sha256,
            dense_score=0.8,
            lexical_score=0.5,
            fused_score=0.03,
            dense_rank=index,
            lexical_rank=index,
            fused_rank=index,
        )
        for index, (item, raw) in enumerate(zip(relevant, evidence, strict=True), start=1)
    )
    retrieval = RetrievalCaseRecordV2(
        query_id=query.query_id,
        run_id=subject.run_id,
        evaluation_run_subject_sha256=subject.digest,
        policy_sha256=subject.retrieval_policy_sha256,
        encoder_space_sha256=subject.encoder_space_sha256,
        index_manifest_sha256=subject.normal_index_manifest_sha256,
        started_monotonic_ns=1,
        finished_monotonic_ns=2,
        decision=RetrievalDecision.RETRIEVE,
        reason_code=None,
        hits=hits,
    )
    answer_text = "\n".join(facts)
    claims = (
        AnswerClaimV2("claim-1", hashlib.sha256(facts[0].encode()).hexdigest(), 0, 10),
        AnswerClaimV2("claim-2", hashlib.sha256(facts[1].encode()).hexdigest(), 11, 20),
    )
    citations = tuple(
        AnswerCitationV2(
            claim.claim_id,
            relevant[1 - index].source_id,
            relevant[1 - index].chunk_id,
            0,
            len(evidence[1 - index]),
            hashlib.sha256(evidence[1 - index].encode()).hexdigest(),
        )
        for index, claim in enumerate(claims)
    )
    answer = AnswerCaseRecordV2(
        query_id=query.query_id,
        run_id=subject.run_id,
        evaluation_run_subject_sha256=subject.digest,
        execution_variant=EvaluationVariant.NORMAL,
        generator_identity_sha256=subject.generator_identity_sha256,
        prompt_template_sha256=subject.prompt_template_sha256,
        decision=EvaluationAnswerDecision.ANSWER,
        reason_code=None,
        answer_utf8=answer_text,
        claims=claims,
        citations=citations,
        normal_index_manifest_sha256=subject.normal_index_manifest_sha256,
        ablation_index_manifest_sha256=None,
        seed=subject.seed,
        decoding_policy_sha256=subject.decoding_policy_sha256,
        started_monotonic_ns=2,
        finished_monotonic_ns=3,
    )
    report = evaluate_quality_v2(
        (query,),
        {query.query_id: retrieval},
        {query.query_id: answer},
        execution_subject=subject,
        split="sealed_test",
        corpus_manifest_sha256=DIGEST,
        retrieval_policy_sha256=DIGEST,
        threshold_policy_sha256=DIGEST,
    )
    assert report["metrics"]["evidence_span_validity_ppm"] == 1_000_000
    assert report["metrics"]["claim_grounding_precision"]["ppm"] == 0


def test_canary_ablation_has_a_real_paired_success_path() -> None:
    base = _query("canary-1", answerable=True, group="canary")
    query = replace(
        base,
        track="canary_ablation",
        canary_value_sha256=hashlib.sha256(b"claim").hexdigest(),
    )
    subject = replace(_subject((query,)), ablation_index_manifest_sha256="f" * 64)
    normal_retrieval = _retrieval(query.query_id, answerable=True, subject=subject)
    normal_answer = _answer(query.query_id, subject=subject)
    ablation_retrieval = RetrievalCaseRecordV2(
        query_id=query.query_id,
        run_id=subject.run_id,
        evaluation_run_subject_sha256=subject.digest,
        policy_sha256=subject.retrieval_policy_sha256,
        encoder_space_sha256=subject.encoder_space_sha256,
        index_manifest_sha256=subject.ablation_index_manifest_sha256,
        started_monotonic_ns=4,
        finished_monotonic_ns=5,
        decision=RetrievalDecision.ABSTAIN,
        reason_code="NO_RELEVANT_EVIDENCE",
        hits=(),
    )
    ablation_answer = AnswerCaseRecordV2(
        query_id=query.query_id,
        run_id=subject.run_id,
        evaluation_run_subject_sha256=subject.digest,
        execution_variant=EvaluationVariant.ABLATION,
        generator_identity_sha256=subject.generator_identity_sha256,
        prompt_template_sha256=subject.prompt_template_sha256,
        decision=EvaluationAnswerDecision.ABSTAIN,
        reason_code="NO_RELEVANT_EVIDENCE",
        answer_utf8=None,
        claims=(),
        citations=(),
        normal_index_manifest_sha256=subject.normal_index_manifest_sha256,
        ablation_index_manifest_sha256=subject.ablation_index_manifest_sha256,
        seed=subject.seed,
        decoding_policy_sha256=subject.decoding_policy_sha256,
        started_monotonic_ns=5,
        finished_monotonic_ns=6,
    )
    report = evaluate_quality_v2(
        (query,),
        {query.query_id: normal_retrieval},
        {query.query_id: normal_answer},
        execution_subject=subject,
        ablation_retrieval_records={query.query_id: ablation_retrieval},
        ablation_answer_records={query.query_id: ablation_answer},
        split="sealed_test",
        corpus_manifest_sha256=subject.corpus_manifest_sha256,
        retrieval_policy_sha256=subject.retrieval_policy_sha256,
        threshold_policy_sha256=subject.threshold_policy_sha256,
    )
    assert report["canary_leakage_count"] == 0
    assert report["metrics"]["recall_at_1_ppm"] == 1_000_000


def test_canary_ablation_rejects_internal_query_id_mismatch() -> None:
    base = _query("canary-1", answerable=True, group="canary")
    query = replace(
        base,
        track="canary_ablation",
        canary_value_sha256=hashlib.sha256(b"claim").hexdigest(),
    )
    subject = replace(_subject((query,)), ablation_index_manifest_sha256="f" * 64)
    normal_retrieval = _retrieval(query.query_id, answerable=True, subject=subject)
    normal_answer = _answer(query.query_id, subject=subject)
    ablation_retrieval = replace(
        normal_retrieval,
        query_id="different-query-r",
        index_manifest_sha256=subject.ablation_index_manifest_sha256,
        decision=RetrievalDecision.ABSTAIN,
        reason_code="NO_RELEVANT_EVIDENCE",
        hits=(),
    )
    ablation_answer = replace(
        _abstain(query.query_id, subject=subject),
        query_id="different-query-a",
        execution_variant=EvaluationVariant.ABLATION,
        ablation_index_manifest_sha256=subject.ablation_index_manifest_sha256,
    )
    with pytest.raises(RetrievalEvaluationError, match="EVALUATION_SUBJECT_MISMATCH"):
        evaluate_quality_v2(
            (query,),
            {query.query_id: normal_retrieval},
            {query.query_id: normal_answer},
            execution_subject=subject,
            ablation_retrieval_records={query.query_id: ablation_retrieval},
            ablation_answer_records={query.query_id: ablation_answer},
            split="sealed_test",
            corpus_manifest_sha256=subject.corpus_manifest_sha256,
            retrieval_policy_sha256=subject.retrieval_policy_sha256,
            threshold_policy_sha256=subject.threshold_policy_sha256,
        )


def test_independent_recompute_cli_preserves_false_abstention(tmp_path: Path) -> None:
    queries = (
        _query("q1", answerable=True, group="g1"),
        _query("q2", answerable=False, group="g2"),
    )
    policy = {"schema_version": "butler.helper1.retrieval-policy.v1", "calibration_state": "APPROVED"}
    threshold = {"schema_version": "butler.helper1.retrieval-threshold-policy.v1"}
    corpus = {"schema_version": "butler.helper1.retrieval-benchmark-manifest.v2"}
    policy_digest = hashlib.sha256(json.dumps(policy, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    threshold_digest = hashlib.sha256(json.dumps(threshold, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    corpus_digest = hashlib.sha256(json.dumps(corpus, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    subject = _subject(
        queries,
        corpus=corpus_digest,
        retrieval_policy=policy_digest,
        threshold_policy=threshold_digest,
    )
    subject = EvaluationRunSubjectV2(
        **{**subject.to_dict(), "decoding_policy_sha256": policy_digest}
    )
    retrieval = tuple(
        _retrieval(query.query_id, answerable=query.answerable, subject=subject) for query in queries
    )
    answers = tuple(_abstain(query.query_id, subject=subject) for query in queries)
    query_path = tmp_path / "queries.jsonl"
    retrieval_path = tmp_path / "retrieval.jsonl"
    answer_path = tmp_path / "answers.jsonl"
    policy_path = tmp_path / "policy.json"
    threshold_path = tmp_path / "threshold.json"
    corpus_path = tmp_path / "corpus.json"
    subject_path = tmp_path / "subject.json"
    output_path = tmp_path / "report.json"
    query_path.write_text(
        "".join(json.dumps(asdict(query), separators=(",", ":")) + "\n" for query in queries),
        encoding="utf-8",
    )
    retrieval_path.write_text(
        "".join(json.dumps(record.to_dict(), separators=(",", ":")) + "\n" for record in retrieval),
        encoding="utf-8",
    )
    answer_path.write_text(
        "".join(json.dumps(record.to_dict(), separators=(",", ":")) + "\n" for record in answers),
        encoding="utf-8",
    )
    policy_path.write_text(json.dumps(policy) + "\n", encoding="utf-8")
    threshold_path.write_text(json.dumps(threshold) + "\n", encoding="utf-8")
    corpus_path.write_text(json.dumps(corpus) + "\n", encoding="utf-8")
    subject_path.write_text(json.dumps(subject.to_dict()) + "\n", encoding="utf-8")
    completed = subprocess.run(
        [
            sys.executable,
            "scripts/ci/helper1_recompute_quality_report.py",
            "--queries",
            str(query_path),
            "--retrieval-cases",
            str(retrieval_path),
            "--answer-cases",
            str(answer_path),
            "--execution-subject",
            str(subject_path),
            "--corpus-manifest",
            str(corpus_path),
            "--retrieval-policy",
            str(policy_path),
            "--threshold-policy",
            str(threshold_path),
            "--output",
            str(output_path),
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stdout
    report = json.loads(output_path.read_text(encoding="utf-8"))
    assert report["metrics"]["abstention_precision"]["ppm"] == 500_000
