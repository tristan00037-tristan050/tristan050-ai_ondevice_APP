from __future__ import annotations

import math
import uuid
from dataclasses import replace

import pytest

from butler_pc_core.helper1.contracts import Claim, RetrievedChunk, sha256_bytes
from butler_pc_core.helper1.evaluation import (
    EvaluationHit,
    EvaluationQuery,
    RelevantEvidence,
    RetrievalEvaluationError,
    evaluate_rankings,
    validate_group_splits,
)
from butler_pc_core.helper1.models import GeneratedDraft
from butler_pc_core.helper1.pipeline import Helper1PipelineError, bind_citations
from butler_pc_core.helper1.retrieval import RetrievalError, RetrievalPolicy


DIGEST = "a" * 64


def _ids() -> tuple[str, str]:
    return str(uuid.uuid4()), str(uuid.uuid4())


def _record(*, split: str = "calibration", group: str = "group:one"):
    workspace, generation = _ids()
    evidence = "근거 문장".encode("utf-8")
    return EvaluationQuery(
        query_id="query:one",
        group_id=group,
        split=split,
        workspace_id=workspace,
        generation_id=generation,
        answerable=True,
        relevant=(
            RelevantEvidence(
                chunk_id="chunk:one",
                source_id="source:one",
                byte_start=0,
                byte_end=len(evidence),
                evidence_sha256=sha256_bytes(evidence),
            ),
        ),
        language="ko",
        document_type="txt",
        difficulty="normal",
    )


def test_unapproved_policy_is_explicitly_uncalibrated() -> None:
    policy = RetrievalPolicy()
    assert not policy.is_calibrated
    assert policy.calibration_state == "DEVELOPMENT_UNCALIBRATED"
    with pytest.raises(RetrievalError, match="BLOCK_RETRIEVAL_POLICY_UNCALIBRATED"):
        RetrievalPolicy(calibration_state="APPROVED")


def test_evaluator_rejects_group_leakage_and_nonfinite_score() -> None:
    calibration = _record()
    sealed = replace(calibration, query_id="query:two", split="sealed_test")
    with pytest.raises(RetrievalEvaluationError, match="BLOCK_EVALUATION_GROUP_LEAKAGE"):
        validate_group_splits((calibration, sealed))
    with pytest.raises(Exception, match="EVALUATION_HIT_SCORE_INVALID"):
        EvaluationHit(
            workspace_id=calibration.workspace_id,
            generation_id=calibration.generation_id,
            chunk_id="chunk:one",
            source_id="source:one",
            score=math.nan,
            content_utf8=b"x",
        )


def test_evaluator_recomputes_leakage_staleness_and_span_from_bytes() -> None:
    record = _record()
    wrong_workspace, stale_generation = _ids()
    hit = EvaluationHit(
        workspace_id=wrong_workspace,
        generation_id=stale_generation,
        chunk_id="chunk:one",
        source_id="source:one",
        score=1.0,
        content_utf8="근거 문장".encode("utf-8"),
    )
    report = evaluate_rankings(
        (record,),
        {record.query_id: (hit,)},
        split="calibration",
        k=1,
        corpus_sha256=DIGEST,
        policy_sha256="b" * 64,
        approved_threshold_policy_sha256=None,
    )
    assert report["gate"] == "BLOCK_RETRIEVAL_POLICY_UNCALIBRATED"
    assert report["metrics"]["wrong_workspace_leakage"] == 1.0
    assert report["metrics"]["stale_generation_rate"] == 1.0
    assert report["metrics"]["evidence_span_validity"] == 1.0


def test_abstention_confusion_matrix_counts_answerable_false_abstention() -> None:
    answerable_empty = replace(_record(), query_id="query:answerable-empty")
    answerable_hit = replace(
        _record(),
        query_id="query:answerable-hit",
        group_id="group:two",
    )
    unanswerable_empty = replace(
        _record(),
        query_id="query:unanswerable-empty",
        group_id="group:three",
        answerable=False,
        relevant=(),
    )
    unanswerable_hit = replace(
        _record(),
        query_id="query:unanswerable-hit",
        group_id="group:four",
        answerable=False,
        relevant=(),
    )
    relevant_hit = EvaluationHit(
        workspace_id=answerable_hit.workspace_id,
        generation_id=answerable_hit.generation_id,
        chunk_id="chunk:one",
        source_id="source:one",
        score=1.0,
        content_utf8="근거 문장".encode("utf-8"),
    )
    irrelevant_hit = EvaluationHit(
        workspace_id=unanswerable_hit.workspace_id,
        generation_id=unanswerable_hit.generation_id,
        chunk_id="chunk:other",
        source_id="source:other",
        score=1.0,
        content_utf8=b"irrelevant",
    )
    records = (
        answerable_empty,
        answerable_hit,
        unanswerable_empty,
        unanswerable_hit,
    )
    rankings = {
        answerable_empty.query_id: (),
        answerable_hit.query_id: (relevant_hit,),
        unanswerable_empty.query_id: (),
        unanswerable_hit.query_id: (irrelevant_hit,),
    }
    report = evaluate_rankings(
        records,
        rankings,
        split="calibration",
        k=1,
        corpus_sha256=DIGEST,
        policy_sha256="b" * 64,
        approved_threshold_policy_sha256="c" * 64,
    )
    assert report["metrics"]["abstention_precision"] == 0.5
    assert report["metrics"]["abstention_recall"] == 0.5
    assert report["gate"] == "BLOCK_RETRIEVAL_POLICY_UNCALIBRATED"

    approved = evaluate_rankings(
        records,
        rankings,
        split="calibration",
        k=1,
        corpus_sha256=DIGEST,
        policy_sha256="b" * 64,
        approved_threshold_policy_sha256="c" * 64,
        approved_calibration_receipt_sha256="d" * 64,
    )
    assert approved["gate"] == "READY_FOR_PROTECTED_THRESHOLD_CHECK"


def test_utf8_citation_span_is_bound_to_workspace_and_generation() -> None:
    workspace, generation = _ids()
    text = "가나다 evidence"
    raw = text.encode("utf-8")
    chunk = RetrievedChunk(
        workspace_id=workspace,
        generation_id=generation,
        chunk_id="chunk:one",
        source_id="source:one",
        text=text,
        dense_score=1.0,
        lexical_score=None,
        fused_score=1.0,
        dense_rank=1,
        lexical_rank=None,
        byte_start=0,
        byte_end=len(raw),
        content_sha256=sha256_bytes(raw),
    )
    claim = Claim("claim:one", text, "chunk:one", 0, len(raw))
    citations, ratio = bind_citations(GeneratedDraft(text, (claim,)), (chunk,))
    assert ratio == 1.0
    assert citations[0].workspace_id == workspace
    assert citations[0].generation_id == generation
    with pytest.raises(Helper1PipelineError, match="CLAIM_EVIDENCE_NOT_UTF8_BOUNDARY"):
        bind_citations(
            GeneratedDraft("가", (Claim("claim:bad", "가", "chunk:one", 1, 3),)),
            (chunk,),
        )
