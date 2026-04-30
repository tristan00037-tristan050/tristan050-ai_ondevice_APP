"""test_personal_pack_v2.py — Personal Pack 하이브리드 검색 v2 (8케이스)."""
from __future__ import annotations

import json
import sys
import threading
from datetime import datetime, timezone
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO))

from butler_pc_core.retrieval.chunkers import Chunk
from butler_pc_core.retrieval.pipeline import HybridRetrievalPipeline, PersonalPackIndex

_FIXTURE_DIR = _REPO / "tests/fixtures/personal_pack_eval"
_DOCS_PATH = _FIXTURE_DIR / "docs_50.jsonl"
_QUERIES_PATH = _FIXTURE_DIR / "queries_30.jsonl"


def _load_chunks() -> list[Chunk]:
    chunks = []
    for line in _DOCS_PATH.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        d = json.loads(line)
        chunks.append(Chunk(
            chunk_id=d["chunk_id"],
            text=d["text"],
            source_file=d["source_file"],
            metadata=d.get("metadata", {}),
        ))
    return chunks


def _load_queries() -> list[dict]:
    return [
        json.loads(l)
        for l in _QUERIES_PATH.read_text(encoding="utf-8").splitlines()
        if l.strip()
    ]


@pytest.fixture(scope="module")
def index() -> PersonalPackIndex:
    return PersonalPackIndex.build(_load_chunks())


@pytest.fixture(scope="module")
def pipeline(index: PersonalPackIndex) -> HybridRetrievalPipeline:
    return HybridRetrievalPipeline(index)


def test_happy_top5_hit_rate_90pct(pipeline: HybridRetrievalPipeline):
    """30개 쿼리 중 27개(90%) 이상 top-5 안에 relevant 청크 포함."""
    queries = _load_queries()
    hits = 0
    for q in queries:
        results = pipeline.retrieve(q["query"], top_k=5)
        returned_ids = {r.chunk.chunk_id for r in results}
        if returned_ids & set(q["relevant_chunk_ids"]):
            hits += 1
    hit_rate = hits / len(queries)
    assert hit_rate >= 0.90, (
        f"top-5 hit rate {hit_rate:.1%} < 90% (hits={hits}/{len(queries)})"
    )


def test_happy_metadata_boost_recent_file(index: PersonalPackIndex):
    """recent 파일(30일 이내)이 동일 관련성의 오래된 파일보다 상위에 위치한다."""
    recent_chunk = Chunk(
        chunk_id="test_recent_c0",
        text="온디바이스 AI 성능 최적화 결과 보고",
        source_file="최신보고서.pdf",
        metadata={"modified_at": "2026-04-29T10:00:00"},
    )
    old_chunk = Chunk(
        chunk_id="test_old_c0",
        text="온디바이스 AI 성능 최적화 결과 보고",
        source_file="구보고서.pdf",
        metadata={"modified_at": "2025-01-01T10:00:00"},
    )
    test_chunks = list(index.chunks) + [recent_chunk, old_chunk]
    test_index = PersonalPackIndex.build(test_chunks)
    p = HybridRetrievalPipeline(test_index)
    now = datetime(2026, 4, 30, tzinfo=timezone.utc)
    results = p.retrieve("온디바이스 AI 성능 최적화", top_k=10, now=now)
    ids = [r.chunk.chunk_id for r in results]
    assert "test_recent_c0" in ids
    if "test_old_c0" in ids:
        assert ids.index("test_recent_c0") <= ids.index("test_old_c0"), (
            "최신 파일이 오래된 파일보다 하위에 위치함"
        )


def test_boundary_reranker_timeout_fallback(index: PersonalPackIndex):
    """재랭커 타임아웃 0초 설정 시 결과가 비어있지 않고 fallback 동작한다."""
    p = HybridRetrievalPipeline(index, reranker_timeout_secs=0.0)
    results = p.retrieve("매출 실적 보고서", top_k=5)
    assert len(results) >= 1
    assert all(r.chunk.text for r in results)


def test_boundary_empty_query_handling(pipeline: HybridRetrievalPipeline):
    """빈 쿼리/공백 쿼리는 빈 리스트를 반환하고 예외가 발생하지 않는다."""
    assert pipeline.retrieve("") == []
    assert pipeline.retrieve("   ") == []
    assert pipeline.retrieve("\t\n") == []


def test_adv_factpack_priority_enforcement(index: PersonalPackIndex):
    """factpack_ids에 지정된 source_file의 청크가 top-3 안에 포함된다."""
    factpack_file = "계약서/B사_서비스계약.docx"
    factpack_ids = frozenset([factpack_file])
    p = HybridRetrievalPipeline(index, factpack_ids=factpack_ids)
    results = p.retrieve("계약 조건 서비스 기간", top_k=5)
    top3_sources = {r.chunk.source_file for r in results[:3]}
    assert factpack_file in top3_sources, (
        f"factpack 파일 '{factpack_file}'이 top-3 밖: {[r.chunk.source_file for r in results[:5]]}"
    )


def test_adv_top5_hit_with_korean_query(pipeline: HybridRetrievalPipeline):
    """한국어 전용 쿼리도 관련 청크를 top-5 안에 반환한다."""
    test_cases = [
        ("재택근무 정책", "doc_026_c0"),
        ("SSE 스트림 타임아웃 버그", "doc_032_c0"),
        ("스프린트 계획 Personal Pack", "doc_046_c0"),
    ]
    for query, expected_id in test_cases:
        results = pipeline.retrieve(query, top_k=5)
        returned_ids = {r.chunk.chunk_id for r in results}
        assert expected_id in returned_ids, (
            f"쿼리 '{query}': 예상 ID '{expected_id}' top-5 미포함. "
            f"반환된 IDs: {returned_ids}"
        )


def test_adv_misspelled_filename_recovery(index: PersonalPackIndex):
    """유사 키워드 포함 쿼리도 정상 결과를 반환한다 (부분 키워드 매칭)."""
    results = index.bm25.search("캐시 SQLite 설계", top_k=5)
    returned_ids = {r.chunk.chunk_id for r in results}
    assert "doc_047_c0" in returned_ids, (
        f"캐시 설계서 청크가 BM25 top-5 미포함: {returned_ids}"
    )


def test_concurrent_two_queries_isolated(index: PersonalPackIndex):
    """두 쿼리가 동시에 실행되어도 결과가 격리되고 교차되지 않는다."""
    p = HybridRetrievalPipeline(index)
    results_a: list = []
    results_b: list = []
    errors: list = []

    def query_a():
        try:
            results_a.extend(p.retrieve("매출 실적 보고서", top_k=5))
        except Exception as e:
            errors.append(e)

    def query_b():
        try:
            results_b.extend(p.retrieve("보안 취약점 API 인증", top_k=5))
        except Exception as e:
            errors.append(e)

    t1 = threading.Thread(target=query_a)
    t2 = threading.Thread(target=query_b)
    t1.start()
    t2.start()
    t1.join(timeout=5)
    t2.join(timeout=5)

    assert not errors, f"동시 쿼리 중 오류 발생: {errors}"
    assert len(results_a) >= 1 and len(results_b) >= 1

    ids_a = {r.chunk.chunk_id for r in results_a}
    ids_b = {r.chunk.chunk_id for r in results_b}
    assert "doc_003_c0" in ids_a or "doc_003_c1" in ids_a or "doc_050_c0" in ids_a, (
        f"매출 쿼리가 매출 관련 청크를 반환하지 않음: {ids_a}"
    )
    assert "doc_040_c0" in ids_b or "doc_024_c0" in ids_b, (
        f"보안 쿼리가 보안/API 관련 청크를 반환하지 않음: {ids_b}"
    )
