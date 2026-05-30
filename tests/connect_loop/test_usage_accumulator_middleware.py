"""PR-B: Usage Accumulator Middleware 검증.

- 순수 빌더(record_usage/build_usage_log) 단위 테스트: PR-A 통첨 불변식 강제, 원문 0,
  매핑 정합, 비매칭 경로 무기록, 스키마 검증.
- real 통합 테스트: helper1 /search 실제 1회 호출 → usage_log 정확히 1건(중복 0) 생성,
  계약 schema validate 통과, raw_text_logged=false / external_send_zero=true,
  policy_decision 존재, integration_mode/real_validation_done 통첨 정합, source_digests 존재.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

pytest.importorskip("jsonschema")
from jsonschema import Draft7Validator

REPO_ROOT = Path(__file__).resolve().parents[2]
USAGE_LOG_SCHEMA = json.loads(
    (REPO_ROOT / "schemas/connect_loop/usage_log_v1_1.schema.json").read_text(encoding="utf-8")
)

from butler_pc_core.sidecar.middleware.usage_accumulator import (  # noqa: E402
    UsageLogStore,
    build_usage_log,
    record_usage,
)

_VALIDATOR = Draft7Validator(USAGE_LOG_SCHEMA)


def _good_source_digest() -> str:
    return "sha256:" + "a" * 64


def _rec(resp_body: dict, *, status: int = 200, path: str = "/v1/helpers/1/search",
         req: bytes = b'{"query":"x","top_k":5}', headers: dict | None = None):
    store = UsageLogStore()
    rec = record_usage(
        path=path, status_code=status, request_body=req,
        response_body=json.dumps(resp_body).encode("utf-8"),
        headers=headers or {}, latency_ms=12.3, store=store,
    )
    return rec, store


# ── 스키마 정합 ──────────────────────────────────────────────────────────────

def test_record_is_schema_valid():
    rec, store = _rec({
        "integration_mode": "real", "real_validation_done": True,
        "results": [{"chunk_id": "c1", "score": 0.9, "source_digest": _good_source_digest()}],
    })
    assert rec is not None
    _VALIDATOR.validate(rec)  # 계약 통과
    assert len(store.records) == 1 and store.dropped == 0


# ── PR-A 통첨 불변식 강제 ────────────────────────────────────────────────────

def test_contract_only_forces_real_validation_done_false():
    # 엔드포인트가 모순(contract_only + real_validation_done=true)을 보고해도 미들웨어가 교정.
    rec, _ = _rec({"integration_mode": "contract_only", "real_validation_done": True, "results": []})
    assert rec["integration_mode"] == "contract_only"
    assert rec["real_validation_done"] is False
    _VALIDATOR.validate(rec)


def test_non_allow_status_forces_contract_only_nonreal():
    # 정책 차단(비 2xx) → policy_decision=deny, contract_only, real_validation_done=false.
    rec, _ = _rec({"integration_mode": "real", "real_validation_done": True}, status=403)
    assert rec["policy_decision"] == "deny"
    assert rec["integration_mode"] == "contract_only"
    assert rec["real_validation_done"] is False
    _VALIDATOR.validate(rec)


def test_real_allow_routed_stays_real():
    rec, _ = _rec({
        "integration_mode": "real", "real_validation_done": True,
        "results": [{"chunk_id": "c1", "score": 0.8, "source_digest": _good_source_digest()}],
    })
    assert rec["integration_mode"] == "real"
    assert rec["real_validation_done"] is True
    assert rec["policy_decision"] == "allow"
    assert rec["endpoint"] != "none"
    assert rec["source_digests"] == [_good_source_digest()]
    _VALIDATOR.validate(rec)


@pytest.mark.parametrize("mode,rvd,status", [
    ("real", True, 200), ("real", False, 200), ("contract_only", True, 200),
    ("contract_only", False, 200), ("real", True, 403), ("real", True, 401),
])
def test_invariant_never_violated(mode, rvd, status):
    rec, _ = _rec({"integration_mode": mode, "real_validation_done": rvd}, status=status)
    _VALIDATOR.validate(rec)
    if rec["real_validation_done"]:
        assert rec["integration_mode"] == "real"
        assert rec["policy_decision"] == "allow"
        assert rec["endpoint"] != "none"
    if rec["integration_mode"] == "contract_only":
        assert rec["real_validation_done"] is False


# ── 원문 0 (digest-only) ─────────────────────────────────────────────────────

def test_no_raw_text_or_local_path_in_record():
    secret = "UNIQUE_RAW_QUERY_PRB_55555"
    rec, _ = _rec(
        {"integration_mode": "real", "real_validation_done": True,
         "results": [{"chunk_id": secret, "score": 0.9, "source_digest": _good_source_digest()}],
         "answer": secret},
        req=json.dumps({"query": secret}).encode("utf-8"),
    )
    blob = json.dumps(rec, ensure_ascii=False)
    assert secret not in blob, "원문이 usage_log 에 유출됨"
    assert "/Users/" not in blob, "로컬 절대경로 유출"
    assert rec["raw_text_logged"] is False
    assert rec["external_send_zero"] is True


# ── 라우트 → intent/box/endpoint 매핑 ───────────────────────────────────────

@pytest.mark.parametrize("path,intent,box,endpoint", [
    ("/v1/helpers/1/search", "memory_search", "helper1", "POST /v1/helpers/1/search"),
    ("/v1/cards/2/rewrite", "form_convert", "2", "POST /v1/cards/2/rewrite"),
    ("/v1/cards/3/draft", "draft_write", "3", "POST /v1/cards/3/draft"),
])
def test_route_mapping(path, intent, box, endpoint):
    rec, _ = _rec({"integration_mode": "contract_only", "real_validation_done": False}, path=path)
    assert (rec["intent_label"], rec["box_id"], rec["endpoint"]) == (intent, box, endpoint)
    _VALIDATOR.validate(rec)


def test_unmatched_path_creates_no_log():
    rec, store = _rec({"x": 1}, path="/health")
    assert rec is None
    assert len(store.records) == 0


# ── const / 고정 필드 ────────────────────────────────────────────────────────

def test_const_fields():
    rec, _ = _rec({"integration_mode": "real", "real_validation_done": True,
                   "results": [{"chunk_id": "c", "score": 1.0, "source_digest": _good_source_digest()}]})
    assert rec["external_send_zero"] is True
    assert rec["raw_text_logged"] is False
    assert rec["learning_event_created"] is False
    assert rec["retention_class"] == "audit_digest_only"
    assert rec["created_by_component"] == "connect_loop.usage_accumulator"
    assert rec["schema_version"] == "usage_log.v1.1"
    assert rec["request_digest"].startswith("sha256:")
    assert rec["result_digest"].startswith("sha256:")


# ── real 통합 검증 (helper1 /search 실제 1회 호출) ───────────────────────────

def _load_sidecar():
    import butler_sidecar
    if not getattr(butler_sidecar, "_FASTAPI_AVAILABLE", False):
        pytest.skip("FastAPI not available")
    return butler_sidecar


def test_real_helper1_search_produces_exactly_one_usage_log():
    import butler_pc_core.sidecar.routes.helper1_search as h1
    if h1.search_integration_mode() != "real":
        pytest.skip("helper1 real 자산 부재 — real 검증 스킵")

    from fastapi.testclient import TestClient
    from butler_pc_core.sidecar.middleware.usage_accumulator import get_store

    mod = _load_sidecar()
    token = mod._TOKEN_MANAGER.generate()
    client = TestClient(mod.app)
    store = get_store()
    store.clear()

    secret = "UNIQUE_QUERY_PRB_REAL_98765"
    resp = client.post(
        "/v1/helpers/1/search",
        json={"query": secret, "top_k": 5},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200, resp.text

    # 공통 미들웨어 1곳 → 정확히 1건(박스별 중복 logging 0)
    assert len(store.records) == 1, f"usage_log 가 정확히 1건이어야 함 (got {len(store.records)})"
    assert store.dropped == 0, "스키마 검증 실패로 드롭된 레코드가 있음"
    rec = store.records[0]

    # 계약 schema validate 통과
    _VALIDATOR.validate(rec)

    # 보안 불변식
    assert rec["raw_text_logged"] is False
    assert rec["external_send_zero"] is True
    blob = json.dumps(rec, ensure_ascii=False)
    assert secret not in blob, "원문 query 가 usage_log 에 유출됨"
    assert "/Users/" not in blob, "로컬 절대경로 유출"

    # 매핑/정책/정합
    assert rec["intent_label"] == "memory_search"
    assert rec["box_id"] == "helper1"
    assert rec["endpoint"] == "POST /v1/helpers/1/search"
    assert rec["policy_decision"] in ("allow", "deny", "review_required")

    # real 검증: 실제 엔드포인트 호출이 real 로 성립 + source_digests 존재
    assert rec["integration_mode"] == "real"
    assert rec["real_validation_done"] is True
    assert len(rec["source_digests"]) > 0, "real 호출의 source_digests 가 존재해야 함"
    for sd in rec["source_digests"]:
        assert sd.startswith("sha256:")

    # 통첨 불변식 위반 0
    if rec["real_validation_done"]:
        assert rec["integration_mode"] == "real"
        assert rec["policy_decision"] == "allow"
        assert rec["endpoint"] != "none"
    if rec["integration_mode"] == "contract_only":
        assert rec["real_validation_done"] is False


def test_real_helper1_search_no_duplicate_across_two_calls():
    import butler_pc_core.sidecar.routes.helper1_search as h1
    if h1.search_integration_mode() != "real":
        pytest.skip("helper1 real 자산 부재 — real 검증 스킵")
    from fastapi.testclient import TestClient
    from butler_pc_core.sidecar.middleware.usage_accumulator import get_store

    mod = _load_sidecar()
    token = mod._TOKEN_MANAGER.generate()
    client = TestClient(mod.app)
    store = get_store()
    store.clear()
    for _ in range(2):
        r = client.post("/v1/helpers/1/search", json={"query": "q", "top_k": 3},
                        headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 200, r.text
    # 호출 2회 → 정확히 2건(호출당 1건, 박스별 중복 0)
    assert len(store.records) == 2, f"호출당 1건이어야 함 (got {len(store.records)})"


# ── Codex P2 재리뷰 (2026-05-30) 회귀 ────────────────────────────────────────

def test_fail_closed_when_validator_unavailable(monkeypatch):
    """jsonschema 미설치/스키마 로드 실패로 검증 불가하면 저장하지 않는다(fail-closed)."""
    import butler_pc_core.sidecar.middleware.usage_accumulator as ua
    monkeypatch.setattr(ua, "_validator", lambda: None)
    store = ua.UsageLogStore()
    rec = ua.record_usage(
        path="/v1/helpers/1/search", status_code=200, request_body=b"{}",
        response_body=b'{"integration_mode":"real","real_validation_done":true,"results":[]}',
        headers={}, latency_ms=1.0, store=store,
    )
    assert rec is None
    assert len(store.records) == 0
    assert store.dropped == 1


def test_non_post_method_on_route_creates_no_log():
    """경로는 같아도 POST 가 아니면(GET/OPTIONS 등) usage_log 미생성 — 메서드 게이팅."""
    from fastapi.testclient import TestClient
    from butler_pc_core.sidecar.middleware.usage_accumulator import get_store
    mod = _load_sidecar()
    token = mod._TOKEN_MANAGER.generate()
    client = TestClient(mod.app)
    store = get_store()
    store.clear()
    r = client.get("/v1/helpers/1/search", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code in (404, 405), f"POST-only 라우트에 GET (got {r.status_code})"
    assert len(store.records) == 0, "메서드 불일치 요청이 usage_log 로 기록됨"
