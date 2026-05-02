# Butler Sidecar — Fact Pack v1 통합 가이드

본 문서는 PR #663에서 생성된 `butler_pc_core/factpack/`을 기존 sidecar 파이프라인에 결합하는 절차를 정리한 것입니다. 작업은 Claude Code에서 직접 수행하시면 됩니다.

---

## 1. 통합 위치

수정 대상 파일은 다음 두 곳입니다.

| 파일 | 변경 내용 |
|---|---|
| `butler_pc_core/sidecar/server.py` | 앱 기동 시 FactPack 1회 로드 + `/generate` 핸들러에서 1차 매칭 시도 |
| `butler_pc_core/sidecar/__init__.py` (선택) | 외부에서 FactPack 인스턴스 주입 가능하도록 export |

---

## 2. 변경 절차

### 2-1. 기동 시 FactPack 로드

`server.py` 상단 import 섹션 + 모듈 레벨 초기화:

```python
from butler_pc_core.factpack import FactPack
from butler_pc_core.factpack.schema import FactPackAuditEntry
from datetime import datetime, timezone

# 모듈 로드 시 1회만 실행 (수~수십 ms 소요, 메모리 ~수 MB)
FACT_PACK = FactPack.from_default_facts_dir()
PACK_VERSION = "factpack-v1"
```

### 2-2. `/generate` 핸들러 패치

기존 SSE 스트림 핸들러 진입부에 다음 분기를 삽입합니다.

```python
@app.post("/generate")
async def generate(req: GenerateRequest):
    async def event_stream():
        # ── (1) FactPack 1차 매칭 ──
        match = FACT_PACK.lookup(req.prompt)
        if match is not None:
            yield sse_event("meta", {
                "source": "factpack",
                "fact_id": match.fact.id,
                "score": round(match.score, 3),
            })
            answer = _format_answer_with_source(match.fact)  # integration/pipeline_patch.py 참조
            yield sse_event("chunk", answer)
            yield sse_event("done", {})
            audit_log.append(FactPackAuditEntry(
                query=req.prompt,
                source="factpack",
                fact_id=match.fact.id,
                score=match.score,
                threshold_used=FACT_PACK.threshold,
                timestamp_iso=datetime.now(timezone.utc).isoformat(),
                pack_version=PACK_VERSION,
            ))
            return

        # ── (2) FactPack 미스 → 기존 LLM 파이프라인 그대로 ──
        yield sse_event("meta", {"source": "llm"})
        async for chunk in llm_pipeline.stream(req.prompt):
            yield sse_event("chunk", chunk)
        yield sse_event("done", {})
        audit_log.append(FactPackAuditEntry(
            query=req.prompt,
            source="llm",
            fact_id=None,
            score=None,
            threshold_used=FACT_PACK.threshold,
            timestamp_iso=datetime.now(timezone.utc).isoformat(),
            pack_version=PACK_VERSION,
        ))

    return EventSourceResponse(event_stream())
```

### 2-3. 클라이언트(웹뷰) 측 표시 로직

기존 SSE 핸들러는 `meta` 이벤트를 무시해도 동작에는 지장이 없습니다. 다만 **출처 배지** 표시를 위해 다음 한 줄을 추가하시는 것을 권장 드립니다.

```javascript
// renderer/main.tsx (혹은 SSE 핸들러)
eventSource.addEventListener("meta", (e) => {
  const meta = JSON.parse(e.data);
  if (meta.source === "factpack") {
    showSourceBadge(`✓ 검증된 사실 (${meta.fact_id})`);
  } else {
    showSourceBadge("AI 생성 응답");
  }
});
```

---

## 3. 검증 방법

### 자동화 가능 (Claude Code에서 직접 검증)

```bash
# 1. 파이썬 단위 테스트 — 40개 PASS 확인
cd butler_pc_core
python -m pytest factpack/../tests/test_factpack.py -v

# 2. sidecar 기동 + curl로 매칭 확인
python -m butler_pc_core.sidecar.server &
sleep 2

curl -N -X POST http://127.0.0.1:8765/generate \
  -H "Content-Type: application/json" \
  -d '{"prompt":"한국의 4대 보험은?"}'
# 기대: meta event source="factpack" 포함, chunk 1회로 답변 즉시 종료
```

### 자동화 불가 (대표님 수동 확인 필요)

다음 항목은 GUI 인터랙션이라 정적 분석이나 curl만으로 완전 검증이 어렵습니다.

- [ ] Butler.app 재빌드(`.dmg`) 후 설치 → 카드 6개 클릭 → "한국의 4대 보험" 질의
- [ ] 응답 박스에 출처 배지 표시 여부
- [ ] LLM 폴백 케이스("회의록 작성해줘")에서 정상 스트리밍 동작
- [ ] 복사 버튼 클릭 시 출처 푸터 포함 여부

---

## 4. 롤백 절차

매칭 결과에 이슈가 발견되면 다음 한 줄만 비활성화하시면 즉시 LLM 전용 동작으로 복귀합니다.

```python
# server.py
match = FACT_PACK.lookup(req.prompt) if False else None  # 임시 비활성화
```

이 경우에도 fact pack 모듈 자체는 메모리에 로드되어 있으므로 다시 활성화해도 재기동 불필요합니다.
