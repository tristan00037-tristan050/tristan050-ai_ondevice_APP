"""PR-B: Usage Accumulator Middleware (사용 축적 미들웨어).

PR-A 에서 머지된 계약 `schemas/connect_loop/usage_log_v1_1.schema.json` (usage_log.v1.1) 를
**소비**한다. 계약(스키마)은 변경하지 않는다.

목적: sidecar endpoint 가 응답한 직후, **단일 공통 미들웨어 한 곳**에서 usage_log 1건을
생성·검증·저장한다. 박스/도우미별로 중복 구현하지 않는다.

보안/불변식:
- 원문(raw query/answer/source text) 저장 0. digest(sha256)만. external 전송 0.
- external_send_zero=true / raw_text_logged=false (계약 const).
- PR-A 통첨 불변식 준수: real_validation_done=true ⟹ integration_mode='real' ∧
  policy_decision='allow' ∧ endpoint!='none'. integration_mode='contract_only' ⟹
  real_validation_done=false. (미들웨어가 생성 시 강제 — 위반 레코드 생성 0.)

범위: 응답이 JSON 인 connect_loop 라우트(helper1 search / box2 rewrite / box3 draft)를
공통 처리한다. `/accounting/classify` 는 SSE StreamingResponse 이므로 본 미들웨어의
버퍼링 대상에서 제외한다(스트리밍 엔드포인트의 usage_log 화는 후속 작업; 여기서 버퍼링하면
스트리밍이 깨진다). intent→box→endpoint 매핑은 PR-A SSOT §3 실측표를 따른다.
"""
from __future__ import annotations

import hashlib
import json
import os
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# ── 계약 스키마 경로 (PR-A 머지본, 변경 금지) ────────────────────────────────
_SCHEMA_PATH = (
    Path(__file__).resolve().parents[3]
    / "schemas" / "connect_loop" / "usage_log_v1_1.schema.json"
)
SCHEMA_VERSION = "usage_log.v1.1"
CREATED_BY = "connect_loop.usage_accumulator"

# ── 라우트 → (intent_label, box_id, endpoint) 실측 매핑 (PR-A SSOT §3) ────────
# 응답이 JSON 인 라우트만 포함(공통 버퍼링 대상). accounting/classify(SSE)는 제외.
_ROUTE_MAP: dict[str, tuple[str, str, str]] = {
    "/v1/helpers/1/search": ("memory_search", "helper1", "POST /v1/helpers/1/search"),
    "/v1/cards/2/rewrite": ("form_convert", "2", "POST /v1/cards/2/rewrite"),
    "/v1/cards/3/draft": ("draft_write", "3", "POST /v1/cards/3/draft"),
}

_VALID_INTEGRATION_MODES = {"real", "contract_only"}


def _sha256(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def _digest_text(text: str) -> str:
    return _sha256(text.encode("utf-8"))


def _now_rfc3339() -> str:
    # UTC 'Z' — 실제 현재 시각은 항상 계약 range(월/일/시/분/초) 를 만족한다.
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# ── 스키마 로드 + schema_hash (런타임 계약 드리프트 감지용) ──────────────────
def _load_schema() -> tuple[dict[str, Any] | None, str]:
    try:
        raw = _SCHEMA_PATH.read_bytes()
    except OSError:
        return None, _sha256(b"")
    try:
        schema = json.loads(raw)
    except json.JSONDecodeError:
        schema = None
    return schema, _sha256(raw)


_SCHEMA, _SCHEMA_HASH = _load_schema()


def _validator():
    """jsonschema Draft7Validator 가 있으면 반환, 없으면 None(검증 생략)."""
    if _SCHEMA is None:
        return None
    try:
        from jsonschema import Draft7Validator
    except Exception:
        return None
    return Draft7Validator(_SCHEMA)


# ── usage_log 저장소 (in-memory; 선택적 JSONL 싱크 — device-local, digest-only) ─
class UsageLogStore:
    """생성된 usage_log 레코드를 모으는 공통 저장소.

    - in-memory `records` (감사/테스트 조회용)
    - 환경변수 `BUTLER_USAGE_LOG_PATH` 가 설정되면 해당 경로에 JSONL append(디바이스 로컬).
      미설정 시 파일 사이드이펙트 없음. 어떤 경우에도 원문/external 전송 0.
    """

    def __init__(self) -> None:
        self.records: list[dict[str, Any]] = []
        self.dropped: int = 0  # 스키마 검증 실패로 저장되지 않은 건수

    def clear(self) -> None:
        self.records.clear()
        self.dropped = 0

    def append(self, record: dict[str, Any]) -> None:
        self.records.append(record)
        path = os.environ.get("BUTLER_USAGE_LOG_PATH")
        if path:
            try:
                p = Path(path)
                p.parent.mkdir(parents=True, exist_ok=True)
                with p.open("a", encoding="utf-8") as f:
                    f.write(json.dumps(record, ensure_ascii=False) + "\n")
            except OSError:
                pass  # 저장 실패가 응답을 깨뜨리지 않는다


_STORE = UsageLogStore()


def get_store() -> UsageLogStore:
    return _STORE


# ── usage_log 1건 생성 (순수 함수 — 테스트 용이) ─────────────────────────────
def build_usage_log(
    *,
    path: str,
    status_code: int,
    request_body: bytes,
    response_body: bytes,
    headers: Any,
    latency_ms: float,
) -> dict[str, Any]:
    """매칭된 connect_loop 라우트의 요청/응답으로 usage_log 1건을 만든다.

    원문은 담지 않는다 — request/response 는 digest 로만 기록한다.
    PR-A 통첨 불변식을 생성 시 강제한다(위반 레코드를 만들지 않는다).
    """
    intent_label, box_id, endpoint = _ROUTE_MAP[path]

    # 응답 파싱(엔드포인트가 보고한 mode/검증/소스 digest 추출). 실패해도 안전 기본값.
    try:
        resp = json.loads(response_body.decode("utf-8")) if response_body else {}
        if not isinstance(resp, dict):
            resp = {}
    except (json.JSONDecodeError, UnicodeDecodeError):
        resp = {}

    # policy_decision: 2xx → allow, 그 외 → deny (정책 우회 0; 차단/오류는 non-real).
    allow = 200 <= status_code < 300
    policy_decision = "allow" if allow else "deny"
    policy_reason_code = "OK" if allow else "POLICY_BLOCKED"

    # 엔드포인트가 보고한 값(있으면) 채택.
    mode = resp.get("integration_mode")
    if mode not in _VALID_INTEGRATION_MODES:
        mode = "contract_only"
    real = bool(resp.get("real_validation_done", False))

    # ── PR-A 통첨 불변식 강제 ────────────────────────────────────────────────
    # real 은 정책 allow + 실제 callable endpoint + integration_mode=real 에서만.
    if (not allow) or endpoint == "none":
        mode = "contract_only"
    if mode != "real":
        real = False

    # source_digests: 응답 results[].source_digest (digest-only). 없으면 [].
    source_digests: list[str] = []
    results = resp.get("results")
    if isinstance(results, list):
        for item in results:
            if isinstance(item, dict):
                sd = item.get("source_digest")
                if isinstance(sd, str) and sd.startswith("sha256:"):
                    source_digests.append(sd)

    # routing_confidence: 라우터(후속 PR) 가 헤더로 전달하면 채택, 없으면 직접 호출=1.0.
    routing_confidence = 1.0
    try:
        hv = headers.get("x-routing-confidence") if headers is not None else None
        if hv is not None:
            v = float(hv)
            if 0.0 <= v <= 1.0:
                routing_confidence = v
    except (TypeError, ValueError):
        pass

    def _id_digest(header_name: str, default: str) -> str:
        val = None
        if headers is not None:
            val = headers.get(header_name)
        return _digest_text(val if val else default)

    request_id = None
    if headers is not None:
        request_id = headers.get("x-request-id")
    if not request_id:
        request_id = "req-" + uuid.uuid4().hex

    learning_candidate = False
    if headers is not None and headers.get("x-learning-candidate") == "1":
        learning_candidate = True

    return {
        "log_id": "ulog-" + uuid.uuid4().hex,
        "timestamp": _now_rfc3339(),
        "request_id": request_id,
        "device_id_digest": _id_digest("x-device-id", "device-local"),
        "tenant_id_digest": _id_digest("x-tenant-id", "tenant-local"),
        "department_id_digest": _id_digest("x-department-id", "department-local"),
        "request_digest": _sha256(request_body or b""),
        "intent_label": intent_label,
        "box_id": box_id,
        "endpoint": endpoint,
        "routing_confidence": routing_confidence,
        "integration_mode": mode,
        "real_validation_done": real,
        "result_digest": _sha256(response_body or b""),
        "source_digests": source_digests,
        "policy_decision": policy_decision,
        "policy_reason_code": policy_reason_code,
        "latency_ms": round(latency_ms, 2),
        "external_send_zero": True,
        "raw_text_logged": False,
        "learning_candidate": learning_candidate,
        "learning_event_created": False,
        "retention_class": "audit_digest_only",
        "created_by_component": CREATED_BY,
        "schema_hash": _SCHEMA_HASH,
        "schema_version": SCHEMA_VERSION,
    }


def record_usage(
    *,
    path: str,
    status_code: int,
    request_body: bytes,
    response_body: bytes,
    headers: Any,
    latency_ms: float,
    store: UsageLogStore | None = None,
) -> dict[str, Any] | None:
    """usage_log 1건 생성 → 스키마 validate → 저장. 반환: 저장된 레코드(또는 None).

    검증 실패 시 저장하지 않는다(비계약 레코드 방출 0). 검증기가 없으면 best-effort 저장.
    """
    if path not in _ROUTE_MAP:
        return None
    store = store or _STORE
    record = build_usage_log(
        path=path,
        status_code=status_code,
        request_body=request_body,
        response_body=response_body,
        headers=headers,
        latency_ms=latency_ms,
    )
    validator = _validator()
    if validator is not None:
        errors = sorted(validator.iter_errors(record), key=lambda e: e.path)
        if errors:
            store.dropped += 1
            return None
    store.append(record)
    return record


# ── FastAPI 등록 (공통 1곳) ──────────────────────────────────────────────────
def add_usage_accumulator_middleware(app: Any) -> None:
    """app 에 usage accumulator HTTP 미들웨어를 1회 등록한다(공통 진입점).

    매칭된 JSON connect_loop 라우트에 대해서만 응답을 버퍼링·재구성하고 usage_log 1건을
    생성한다. 비매칭/스트리밍 응답은 손대지 않는다(중복 logging 0).
    """
    from starlette.responses import Response

    @app.middleware("http")
    async def _usage_accumulator(request, call_next):  # type: ignore[no-untyped-def]
        path = request.url.path
        if path not in _ROUTE_MAP:
            return await call_next(request)

        # 요청 본문은 미리 읽어둔다(Starlette 가 캐시 → 다운스트림 핸들러도 그대로 읽음).
        try:
            request_body = await request.body()
        except Exception:
            request_body = b""

        start = time.perf_counter()
        response = await call_next(request)
        latency_ms = (time.perf_counter() - start) * 1000.0

        # 스트리밍 응답은 버퍼링하지 않는다(있다면 그대로 통과).
        if not hasattr(response, "body_iterator"):
            return response

        chunks = [section async for section in response.body_iterator]
        body = b"".join(
            c if isinstance(c, (bytes, bytearray)) else str(c).encode("utf-8") for c in chunks
        )

        try:
            record_usage(
                path=path,
                status_code=response.status_code,
                request_body=request_body,
                response_body=body,
                headers=request.headers,
                latency_ms=latency_ms,
            )
        except Exception:
            # usage_log 생성 실패가 사용자 응답을 깨뜨리지 않는다(fail-open on logging only).
            pass

        # body_iterator 가 소진되었으므로 동일 본문으로 응답을 재구성한다.
        media_type = response.media_type
        new_headers = dict(response.headers)
        return Response(
            content=body,
            status_code=response.status_code,
            headers=new_headers,
            media_type=media_type,
        )
