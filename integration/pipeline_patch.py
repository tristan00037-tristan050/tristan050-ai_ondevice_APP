"""
Butler sidecar 파이프라인 통합 패치 — Fact Pack v1

이 모듈은 Butler sidecar의 기존 generate 파이프라인 앞단에
FactPack 1차 응답 + LLM 폴백 구조를 삽입하기 위한 참조 구현입니다.

통합 위치:
  butler_pc_core/sidecar/server.py 의 /generate 핸들러 내부에서
  resolve_response()를 호출하도록 한 줄 삽입.

핵심 정책:
  1) FactPack hit (score ≥ threshold) → factpack 응답 즉시 반환, LLM 호출 0회
  2) FactPack miss → 기존 LLM 파이프라인 그대로 실행
  3) 모든 응답에 source 메타 부착 (감사 로그용)
  4) 외부 API 호출 0건 (온디바이스 원칙 준수)
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Awaitable, Callable, Optional, Tuple

from butler_pc_core.factpack import (
    Fact,
    FactMatch,
    FactPack,
    FactPackAuditEntry,
)


# ─────────────────────────────────────────────────────────────────────
# 응답 컨테이너 (sidecar 응답 스키마와 호환)
# ─────────────────────────────────────────────────────────────────────


class ResolvedResponse:
    """파이프라인 결과. sidecar의 SSE 이벤트로 변환되어 클라이언트에 전송됨."""

    __slots__ = ("text", "source", "fact_id", "score", "audit")

    def __init__(
        self,
        text: str,
        source: str,
        fact_id: Optional[str] = None,
        score: Optional[float] = None,
        audit: Optional[FactPackAuditEntry] = None,
    ) -> None:
        self.text = text
        self.source = source  # "factpack" | "llm"
        self.fact_id = fact_id
        self.score = score
        self.audit = audit

    def to_event_meta(self) -> dict:
        """SSE meta 이벤트용 dict. 클라이언트가 출처 배지 표시에 사용."""
        meta = {"source": self.source}
        if self.fact_id:
            meta["fact_id"] = self.fact_id
        if self.score is not None:
            meta["score"] = round(self.score, 3)
        return meta


# ─────────────────────────────────────────────────────────────────────
# 메인 파이프라인 진입점
# ─────────────────────────────────────────────────────────────────────


# LLM 호출 콜러블 시그니처: (query) -> str (전체 응답).
# sidecar 측에서 SSE 스트리밍으로 변환할 때는 generator 변형을 사용해도 됨.
LLMCaller = Callable[[str], Awaitable[str]]


async def resolve_response(
    query: str,
    fact_pack: FactPack,
    llm_caller: LLMCaller,
    pack_version: str = "factpack-v1",
) -> ResolvedResponse:
    """쿼리에 대한 최종 응답을 결정.

    절차:
      1) FactPack 매칭 시도 (1~2ms 수준)
      2) 매칭 성공 → factpack 답변 즉시 반환
      3) 매칭 실패 → LLM 호출, 결과 반환

    Args:
        query: 사용자 입력 원문 (정규화 전).
        fact_pack: 로드된 FactPack 인스턴스.
        llm_caller: LLM 호출 비동기 함수.
        pack_version: 감사 로그에 기록할 fact pack 버전.

    Returns:
        ResolvedResponse — 응답 본문 + 출처 메타 + 감사 로그 항목.
    """
    timestamp = datetime.now(timezone.utc).isoformat()

    # 1. FactPack 매칭 시도
    match: Optional[FactMatch] = fact_pack.lookup(query)

    if match is not None:
        fact: Fact = match.fact
        # 답변 본문에 출처 태그 자동 부착 (베타 신뢰도 강화 + 환각 0 보장)
        answer_with_source = _format_answer_with_source(fact)

        audit = FactPackAuditEntry(
            query=query,
            source="factpack",
            fact_id=fact.id,
            score=match.score,
            threshold_used=fact_pack.threshold,
            timestamp_iso=timestamp,
            pack_version=pack_version,
        )

        return ResolvedResponse(
            text=answer_with_source,
            source="factpack",
            fact_id=fact.id,
            score=match.score,
            audit=audit,
        )

    # 2. FactPack 미스 — LLM 폴백
    llm_text = await llm_caller(query)

    audit = FactPackAuditEntry(
        query=query,
        source="llm",
        fact_id=None,
        score=None,
        threshold_used=fact_pack.threshold,
        timestamp_iso=timestamp,
        pack_version=pack_version,
    )

    return ResolvedResponse(
        text=llm_text,
        source="llm",
        audit=audit,
    )


# ─────────────────────────────────────────────────────────────────────
# 출력 포매팅
# ─────────────────────────────────────────────────────────────────────


def _format_answer_with_source(fact: Fact) -> str:
    """fact 답변에 출처 푸터를 자동 부착.

    형식:
        <답변 본문>

        ─────────
        출처: <source> (<verified_at> 기준)
        <source_url>
    """
    lines = [fact.answer.rstrip(), "", "─────────"]
    lines.append(f"출처: {fact.source} ({fact.verified_at} 기준)")
    if fact.source_doc:
        lines.append(f"근거 문서: {fact.source_doc}")
    if fact.source_url:
        lines.append(fact.source_url)
    if fact.expires_at:
        lines.append(f"※ 본 답변은 {fact.expires_at}까지 유효 (이후 재검증 필요)")
    return "\n".join(lines)


# ─────────────────────────────────────────────────────────────────────
# sidecar /generate 핸들러 통합 예시 (참조용)
# ─────────────────────────────────────────────────────────────────────
# 기존 코드:
#
#     @app.post("/generate")
#     async def generate(req: GenerateRequest):
#         async def event_stream():
#             async for chunk in llm_pipeline.stream(req.prompt):
#                 yield sse_event("chunk", chunk)
#             yield sse_event("done", {})
#         return EventSourceResponse(event_stream())
#
# 패치 후:
#
#     # 앱 시작 시 1회 로드 (FactPack은 메모리 ~수MB)
#     FACT_PACK = FactPack.from_default_facts_dir()
#
#     @app.post("/generate")
#     async def generate(req: GenerateRequest):
#         async def event_stream():
#             # 1. FactPack 1차 시도
#             match = FACT_PACK.lookup(req.prompt)
#             if match is not None:
#                 yield sse_event("meta", {
#                     "source": "factpack",
#                     "fact_id": match.fact.id,
#                     "score": round(match.score, 3),
#                 })
#                 # 답변을 단일 chunk로 즉시 송출 (1~2ms)
#                 yield sse_event("chunk", _format_answer_with_source(match.fact))
#                 yield sse_event("done", {})
#                 audit_log.append(FactPackAuditEntry(
#                     query=req.prompt,
#                     source="factpack",
#                     fact_id=match.fact.id,
#                     score=match.score,
#                     threshold_used=FACT_PACK.threshold,
#                     timestamp_iso=datetime.now(timezone.utc).isoformat(),
#                     pack_version="factpack-v1",
#                 ))
#                 return
#
#             # 2. FactPack 미스 — 기존 LLM 파이프라인
#             yield sse_event("meta", {"source": "llm"})
#             async for chunk in llm_pipeline.stream(req.prompt):
#                 yield sse_event("chunk", chunk)
#             yield sse_event("done", {})
#             audit_log.append(FactPackAuditEntry(
#                 query=req.prompt,
#                 source="llm",
#                 fact_id=None,
#                 score=None,
#                 threshold_used=FACT_PACK.threshold,
#                 timestamp_iso=datetime.now(timezone.utc).isoformat(),
#                 pack_version="factpack-v1",
#             ))
#
#         return EventSourceResponse(event_stream())
