"""
tests/butler_pc_core/test_partial_result_serialization.py
==========================================================
P1 회귀 테스트: Partial Result 안전 직렬화 (5 케이스)
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

# sys.path 보장
REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import pytest
from butler_pc_core.runtime.timeout_controller import (
    ChunkResult,
    PartialResultError,
    TimeoutController,
    _safe_json_default,
)


# ---------------------------------------------------------------------------
# 헬퍼: 중단 트리거 후 생성된 partial_result 파일 읽기
# ---------------------------------------------------------------------------
def _abort_and_read(tmp_path: Path, content) -> dict:
    """청크 1개를 저장한 뒤 cancel() → partial_result JSON 반환."""
    ctrl = TimeoutController("t-ser", tmp_path, hard_timeout=30, chunk_timeout=10)
    with ctrl.run_chunk(0) as ctx:
        ctx.set_result(content)
    ctrl.cancel()
    try:
        ctrl.check_hard_timeout()
    except PartialResultError as e:
        return json.loads(Path(e.partial_path).read_text(encoding="utf-8"))
    pytest.fail("PartialResultError가 발생하지 않았습니다.")


# ---------------------------------------------------------------------------
# 케이스 1: chunk.content가 set → 안전 직렬화 성공
# ---------------------------------------------------------------------------
class TestSetContent:
    def test_set_serializes_safely(self, tmp_path):
        data = _abort_and_read(tmp_path, {1, 2, 3})
        chunks = data["completed_chunks"]
        assert len(chunks) == 1
        c = chunks[0]["content"]
        # _safe_json_default 가 {"__type__": "set", "values": [...]} 로 변환
        assert c["__type__"] == "set"
        # sorted(key=str) 결과: 정수 그대로 보존 (JSON 역직렬화 후에도 int)
        assert sorted(c["values"]) == [1, 2, 3]


# ---------------------------------------------------------------------------
# 케이스 2: chunk.content가 bytes → 안전 직렬화 성공
# ---------------------------------------------------------------------------
class TestBytesContent:
    def test_bytes_serializes_safely(self, tmp_path):
        raw = b"\x00\xff\xab" * 20
        data = _abort_and_read(tmp_path, raw)
        c = data["completed_chunks"][0]["content"]
        assert c["__type__"] == "bytes"
        assert c["size"] == len(raw)
        assert isinstance(c["preview"], str)  # hex string


# ---------------------------------------------------------------------------
# 케이스 3: dict 안에 set 중첩 → 안전 직렬화 성공
# ---------------------------------------------------------------------------
class TestNestedSetContent:
    def test_nested_set_in_dict(self, tmp_path):
        content = {"tags": {10, 20, 30}, "label": "test"}
        data = _abort_and_read(tmp_path, content)
        c = data["completed_chunks"][0]["content"]
        assert c["tags"]["__type__"] == "set"
        assert c["label"] == "test"


# ---------------------------------------------------------------------------
# 케이스 4: 직렬화 자체 불가 객체 → fallback 파일 생성
# ---------------------------------------------------------------------------
class TestUnserializableFallback:
    def test_fallback_file_created(self, tmp_path):
        """
        _safe_json_default 도 처리 못하는 극단적 케이스를 시뮬레이션:
        json.dumps 의 default 콜백이 예외를 던지도록 monkeypatching.
        """
        import butler_pc_core.runtime.timeout_controller as tc_mod

        original = tc_mod._safe_json_default

        def _always_raise(obj):
            raise TypeError("절대 직렬화 불가")

        tc_mod._safe_json_default = _always_raise
        try:
            ctrl = TimeoutController("t-fail", tmp_path, hard_timeout=30, chunk_timeout=10)
            with ctrl.run_chunk(0) as ctx:
                ctx.set_result(object())  # 직렬화 불가 객체
            ctrl.cancel()
            try:
                ctrl.check_hard_timeout()
            except PartialResultError as e:
                p = Path(e.partial_path)
                assert p.exists(), "fallback 파일이 생성되지 않았습니다"
                fb = json.loads(p.read_text(encoding="utf-8"))
                assert fb.get("fallback") is True
                assert "serialization_error" in fb
                assert fb["completed_count"] >= 0
        finally:
            tc_mod._safe_json_default = original


# ---------------------------------------------------------------------------
# 케이스 5: 정상 dict 값 → 기존 동작 보존
# ---------------------------------------------------------------------------
class TestNormalDictContent:
    def test_normal_dict_preserved(self, tmp_path):
        content = {"answer": "hello", "score": 0.95, "items": [1, 2, 3]}
        data = _abort_and_read(tmp_path, content)
        c = data["completed_chunks"][0]["content"]
        assert c == content
        assert data["abort_reason"] == "cancelled"
        assert data["partial"] is True
