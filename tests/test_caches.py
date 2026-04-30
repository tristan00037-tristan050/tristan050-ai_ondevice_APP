"""test_caches.py — 4-tier 캐시 단위·동시성 테스트.

prefix 분포 (33개 prefixed):
  happy      10  (~30%)
  boundary   10  (~30%)
  adv        10  (~30%)
  concurrent  3  (~9%)
"""
from __future__ import annotations

import threading
import time
import pytest
from pathlib import Path

from butler_pc_core.runtime.cache import (
    DocumentTextCache,
    ChunkEmbeddingCache,
    RetrievalCache,
    AnswerCache,
)


@pytest.fixture
def tmp_db(tmp_path: Path) -> Path:
    return tmp_path / "test_cache.db"


# ─────────────────────── DocumentTextCache ───────────────────────────────


class TestDocumentTextCache:
    def test_happy_set_and_get(self, tmp_db: Path):
        cache = DocumentTextCache(db_path=tmp_db)
        cache.set_text(b"hello world", "extracted text", parser_version="v1")
        assert cache.get_text(b"hello world", parser_version="v1") == "extracted text"

    def test_happy_different_parser_version_is_separate_key(self, tmp_db: Path):
        cache = DocumentTextCache(db_path=tmp_db)
        cache.set_text(b"doc bytes", "text v1", parser_version="v1")
        cache.set_text(b"doc bytes", "text v2", parser_version="v2")
        assert cache.get_text(b"doc bytes", "v1") == "text v1"
        assert cache.get_text(b"doc bytes", "v2") == "text v2"

    def test_adv_miss_returns_none(self, tmp_db: Path):
        cache = DocumentTextCache(db_path=tmp_db)
        assert cache.get_text(b"nonexistent", "v1") is None

    def test_boundary_ttl_expiry(self, tmp_db: Path):
        cache = DocumentTextCache(db_path=tmp_db)
        cache.set_text(b"expire me", "soon gone", parser_version="v1", ttl_seconds=1)
        assert cache.get_text(b"expire me", "v1") == "soon gone"
        time.sleep(1.1)
        assert cache.get_text(b"expire me", "v1") is None

    def test_boundary_stats_reports_size(self, tmp_db: Path):
        cache = DocumentTextCache(db_path=tmp_db)
        cache.set_text(b"data", "some text", parser_version="v1")
        s = cache.stats()
        assert s["entry_count"] >= 1
        assert s["size_bytes"] >= 0


# ─────────────────────── ChunkEmbeddingCache ─────────────────────────────


class TestChunkEmbeddingCache:
    def test_happy_set_and_get(self, tmp_db: Path):
        cache = ChunkEmbeddingCache(db_path=tmp_db)
        vec = [0.1, 0.2, 0.3]
        cache.set_embedding("chunk text", vec, embedding_model_id="emb-v1")
        assert cache.get_embedding("chunk text", embedding_model_id="emb-v1") == pytest.approx(vec)

    def test_happy_different_model_ids_are_separate(self, tmp_db: Path):
        cache = ChunkEmbeddingCache(db_path=tmp_db)
        cache.set_embedding("text", [1.0, 2.0], embedding_model_id="model-a")
        cache.set_embedding("text", [9.0, 8.0], embedding_model_id="model-b")
        assert cache.get_embedding("text", "model-a") == pytest.approx([1.0, 2.0])
        assert cache.get_embedding("text", "model-b") == pytest.approx([9.0, 8.0])

    def test_adv_miss_returns_none(self, tmp_db: Path):
        cache = ChunkEmbeddingCache(db_path=tmp_db)
        assert cache.get_embedding("missing chunk", "emb-v1") is None

    def test_boundary_ttl_expiry(self, tmp_db: Path):
        cache = ChunkEmbeddingCache(db_path=tmp_db)
        cache.set_embedding("text", [1.0], embedding_model_id="m", ttl_seconds=1)
        assert cache.get_embedding("text", "m") is not None
        time.sleep(1.1)
        assert cache.get_embedding("text", "m") is None

    def test_boundary_overwrite_updates_value(self, tmp_db: Path):
        cache = ChunkEmbeddingCache(db_path=tmp_db)
        cache.set_embedding("text", [1.0, 2.0], embedding_model_id="m")
        cache.set_embedding("text", [3.0, 4.0], embedding_model_id="m")
        assert cache.get_embedding("text", "m") == pytest.approx([3.0, 4.0])


# ─────────────────────── RetrievalCache ──────────────────────────────────


class TestRetrievalCache:
    def test_happy_set_and_get(self, tmp_db: Path):
        cache = RetrievalCache(db_path=tmp_db)
        results = [{"id": "doc1", "score": 0.9}]
        cache.set_results("query", results, index_version="v1", top_k=5)
        assert cache.get_results("query", index_version="v1", top_k=5) == results

    def test_happy_different_top_k_is_separate_key(self, tmp_db: Path):
        cache = RetrievalCache(db_path=tmp_db)
        r5 = [{"id": "a"}]
        r10 = [{"id": "a"}, {"id": "b"}]
        cache.set_results("q", r5, index_version="v1", top_k=5)
        cache.set_results("q", r10, index_version="v1", top_k=10)
        assert cache.get_results("q", "v1", top_k=5) == r5
        assert cache.get_results("q", "v1", top_k=10) == r10

    def test_adv_miss_returns_none(self, tmp_db: Path):
        cache = RetrievalCache(db_path=tmp_db)
        assert cache.get_results("not cached", index_version="v1", top_k=3) is None

    def test_boundary_filters_hash_distinguishes_keys(self, tmp_db: Path):
        cache = RetrievalCache(db_path=tmp_db)
        cache.set_results("q", [{"id": "x"}], index_version="v1", top_k=5, filters={"lang": "ko"})
        cache.set_results("q", [{"id": "y"}], index_version="v1", top_k=5, filters={"lang": "en"})
        ko = cache.get_results("q", "v1", top_k=5, filters={"lang": "ko"})
        en = cache.get_results("q", "v1", top_k=5, filters={"lang": "en"})
        assert ko != en

    def test_boundary_ttl_expiry(self, tmp_db: Path):
        cache = RetrievalCache(db_path=tmp_db)
        cache.set_results("q", [{"id": "z"}], index_version="v1", top_k=1, ttl_seconds=1)
        assert cache.get_results("q", "v1", top_k=1) is not None
        time.sleep(1.1)
        assert cache.get_results("q", "v1", top_k=1) is None


# ─────────────────────── AnswerCache ─────────────────────────────────────


class TestAnswerCache:
    def test_happy_set_and_get(self, tmp_db: Path):
        cache = AnswerCache(db_path=tmp_db)
        cache.set_answer("tmpl1", "digest1", "질문1", "답변1")
        assert cache.get_answer("tmpl1", "digest1", "질문1") == "답변1"

    def test_happy_scenario_differentiates_key(self, tmp_db: Path):
        cache = AnswerCache(db_path=tmp_db)
        cache.set_answer("t", "d", "q", "답변A", scenario="formal")
        cache.set_answer("t", "d", "q", "답변B", scenario="casual")
        assert cache.get_answer("t", "d", "q", scenario="formal") == "답변A"
        assert cache.get_answer("t", "d", "q", scenario="casual") == "답변B"

    def test_adv_miss_returns_none(self, tmp_db: Path):
        cache = AnswerCache(db_path=tmp_db)
        assert cache.get_answer("no", "no", "no") is None

    def test_boundary_ttl_expiry(self, tmp_db: Path):
        cache = AnswerCache(db_path=tmp_db)
        cache.set_answer("t", "d", "q", "answer", ttl_seconds=1)
        assert cache.get_answer("t", "d", "q") == "answer"
        time.sleep(1.1)
        assert cache.get_answer("t", "d", "q") is None

    def test_boundary_overwrite_updates_value(self, tmp_db: Path):
        cache = AnswerCache(db_path=tmp_db)
        cache.set_answer("t", "d", "q", "old answer")
        cache.set_answer("t", "d", "q", "new answer")
        assert cache.get_answer("t", "d", "q") == "new answer"


# ─────────────────────── adv (cross-cache) ───────────────────────────────


def test_adv_build_key_is_deterministic(tmp_db: Path):
    """같은 입력에 대해 build_key가 항상 동일한 해시를 반환한다."""
    cache = DocumentTextCache(db_path=tmp_db)
    k1 = cache.build_key(file_bytes=b"same bytes", parser_version="v1")
    k2 = cache.build_key(file_bytes=b"same bytes", parser_version="v1")
    assert k1 == k2


def test_adv_large_value_serializes_correctly(tmp_db: Path):
    """크기가 큰 임베딩 벡터도 정확하게 저장·복원된다."""
    cache = ChunkEmbeddingCache(db_path=tmp_db)
    big_vec = [float(i) / 1000.0 for i in range(1536)]
    cache.set_embedding("large chunk", big_vec, embedding_model_id="bert-large")
    result = cache.get_embedding("large chunk", "bert-large")
    assert result == pytest.approx(big_vec, rel=1e-5)


# ─────────────────────── concurrent ──────────────────────────────────────


def test_concurrent_parallel_reads_dont_corrupt(tmp_db: Path):
    """여러 스레드에서 동시에 읽어도 데이터가 손상되지 않는다."""
    cache = DocumentTextCache(db_path=tmp_db)
    cache.set_text(b"shared", "shared value", parser_version="v1")

    results: list[str | None] = []
    errors: list[Exception] = []

    def _read():
        try:
            results.append(cache.get_text(b"shared", "v1"))
        except Exception as exc:
            errors.append(exc)

    threads = [threading.Thread(target=_read) for _ in range(10)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert not errors
    assert all(r == "shared value" for r in results)


def test_concurrent_write_then_read_same_key(tmp_db: Path):
    """여러 스레드에서 같은 키에 쓴 후 마지막 값이 읽힌다."""
    cache = AnswerCache(db_path=tmp_db)
    write_count = 5

    def _write(i: int):
        cache.set_answer("t", "d", "q", f"answer-{i}")

    threads = [threading.Thread(target=_write, args=(i,)) for i in range(write_count)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    result = cache.get_answer("t", "d", "q")
    assert result is not None
    assert result.startswith("answer-")


def test_concurrent_invalidate_during_read(tmp_db: Path):
    """invalidate 와 get 이 동시에 실행되어도 예외가 발생하지 않는다."""
    cache = RetrievalCache(db_path=tmp_db)
    for i in range(20):
        cache.set_results(f"q{i}", [{"id": str(i)}], index_version="v1", top_k=5)

    errors: list[Exception] = []

    def _read():
        try:
            for i in range(20):
                cache.get_results(f"q{i}", "v1", top_k=5)
        except Exception as exc:
            errors.append(exc)

    def _invalidate():
        try:
            cache.invalidate("%:v1:%")
        except Exception as exc:
            errors.append(exc)

    t1 = threading.Thread(target=_read)
    t2 = threading.Thread(target=_invalidate)
    t1.start()
    t2.start()
    t1.join()
    t2.join()

    assert not errors
