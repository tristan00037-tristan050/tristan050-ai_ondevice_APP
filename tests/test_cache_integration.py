"""test_cache_integration.py — 캐시 통합 테스트 (3 cases)."""
from __future__ import annotations

import pytest
from pathlib import Path

from butler_pc_core.runtime.cache import (
    DocumentTextCache,
    ChunkEmbeddingCache,
    AnswerCache,
)


@pytest.fixture
def tmp_db(tmp_path: Path) -> Path:
    return tmp_path / "integration.db"


def test_integration_shared_db_tables_do_not_collide(tmp_db: Path):
    """같은 DB 파일을 쓰는 두 캐시가 서로의 키를 간섭하지 않는다."""
    doc_cache = DocumentTextCache(db_path=tmp_db)
    ans_cache = AnswerCache(db_path=tmp_db)

    doc_cache.set_text(b"bytes", "document text", parser_version="v1")
    ans_cache.set_answer("tmpl", "digest", "question", "answer text")

    assert doc_cache.get_text(b"bytes", "v1") == "document text"
    assert ans_cache.get_answer("tmpl", "digest", "question") == "answer text"
    assert doc_cache.stats()["entry_count"] == 1
    assert ans_cache.stats()["entry_count"] == 1


def test_integration_invalidate_clears_matching_entries(tmp_db: Path):
    """invalidate(pattern) 이 패턴 일치 항목만 지운다."""
    cache = ChunkEmbeddingCache(db_path=tmp_db)
    cache.set_embedding("text A", [1.0, 2.0], embedding_model_id="model-old")
    cache.set_embedding("text B", [3.0, 4.0], embedding_model_id="model-old")
    cache.set_embedding("text C", [5.0, 6.0], embedding_model_id="model-new")

    deleted = cache.invalidate(pattern="%:model-old:%")
    assert deleted == 2

    assert cache.get_embedding("text A", "model-old") is None
    assert cache.get_embedding("text B", "model-old") is None
    assert cache.get_embedding("text C", "model-new") == pytest.approx([5.0, 6.0])


def test_integration_stats_reflects_stored_data(tmp_db: Path):
    """stats() 가 실제 저장된 데이터를 정확히 반영한다."""
    cache = DocumentTextCache(db_path=tmp_db)
    assert cache.stats()["entry_count"] == 0

    cache.set_text(b"file1", "text one", parser_version="v1")
    cache.set_text(b"file2", "text two", parser_version="v1")
    s = cache.stats()
    assert s["entry_count"] == 2
    assert s["size_bytes"] > 0
