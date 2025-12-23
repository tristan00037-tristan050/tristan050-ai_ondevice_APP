# R10-S5 P1: Quality/UX/Performance 개선

## 목표
R10-S5 P0 완료 후, 품질/UX/성능 개선 작업을 결정적 게이트(verify 스크립트)로 쪼개 착수

## P1 작업 목록 (우선순위 고정)

### P1-1: Retriever 품질 개선 (결정성 유지)
**DoD:**
- 픽스처 기준 Top-K 적중률 개선
- 동일 입력 동일 결과(결정성) 보장

**Gate:**
- `scripts/verify_rag_retrieval.sh`에 "품질 점수/기준"을 숫자로 넣고 PASS/FAIL
- `scripts/verify_telemetry_rag_meta_only.sh` PASS 필수

#### P1-1 Gate Criteria (Numeric KPI, 회귀 방지선)

P1-1은 "Retriever 품질 개선(결정성 유지)"이며, 완료 판정은 `scripts/verify_rag_retrieval.sh` PASS로만 한다.
(추가로 텔레메트리 가드는 `scripts/verify_telemetry_rag_meta_only.sh` PASS가 필수)

##### 0) Hard Gates (무조건 0이어야 함)
- **결정성(Determinism):**
  - `determinismMismatchCount == 0`
  - (동일 fixture/query set 2회 연속 실행 시 Top-K docId 시그니처가 완전히 동일)
- **Network 0 (Mock/Offline 원칙):**
  - `networkRequestCount == 0`
- **Privacy(meta-only):**
  - `telemetryBannedKeysLeakCount == 0`
  - (prompt/text/message/content/body/snippet/context/raw/input/output 등 "원문 키" 0)

##### 1) Quality Gates (회귀만 차단하는 수준)
###### 권장 방식: Baseline 대비 허용오차(Tolerance)로 회귀 차단
- **baseline 파일:** `docs/ops/r10-s5-p1-1-retrieval-baseline.json` (main에서 1회 생성 후 커밋)
- 현재 실행 결과(metrics)와 baseline을 비교해 아래 조건이면 FAIL

**품질 지표(각각):**
- `hitAt5  >= baseline.hitAt5  - 0.05`   (5pp 이상 하락하면 FAIL)
- `hitAt10 >= baseline.hitAt10 - 0.03`   (3pp 이상 하락하면 FAIL)
- `mrrAt10 >= baseline.mrrAt10 - 0.05`   (0.05 이상 하락하면 FAIL)
- `noResultRate <= baseline.noResultRate + 0.05`  (5pp 이상 증가하면 FAIL)

※ fixture/query 수가 매우 적어 퍼센트가 거칠게 움직이면,
   "허용 miss 건수"로도 병행:
   - `missCountAt5  <= baseline.missCountAt5  + 1`
   - `missCountAt10 <= baseline.missCountAt10 + 1`
   - `noResultCount <= baseline.noResultCount + 1`

###### 안전장치(절대 바닥값) — baseline이 낮아도 최소 품질은 강제
- `hitAt5  >= 0.60`
- `hitAt10 >= 0.75`
- `noResultRate <= 0.20`

(의미: "완전 붕괴"만 막고, 나머지는 baseline 대비 회귀만 차단)

##### 2) Performance Gates (너무 빡세지 않게 상한만)
Retriever는 품질 개선이 목적이므로, 성능은 "대형 회귀"만 막는다.

- `p95RetrieveMs <= max(baseline.p95RetrieveMs * 1.5, baseline.p95RetrieveMs + 100)`
- `p99RetrieveMs <= max(baseline.p99RetrieveMs * 2.0, baseline.p99RetrieveMs + 200)`

**절대 상한(안전장치):**
- `p95RetrieveMs <= 500ms`
- `p99RetrieveMs <= 1000ms`

(측정 환경 편차를 고려한 넉넉한 상한. 이 이상이면 UX 회귀로 간주)

##### 3) 증빙(필수)
- verify 스크립트 실행 로그 1회 + 결과 JSON(가능하면) 을 `docs/ops/`에 남기고 커밋한다.
- P1-1 종료 보고에는 다음 중 1개 이상을 포함:
  - baseline 대비 비교 결과(수치)
  - missCount/noResultCount 변화
  - 결정성/Network/Privacy(0) 확인 결과

**숫자 추천값 요약(핵심만)**
- 결정성/Network/Privacy는 0 고정: `mismatch=0`, `network=0`, `bannedKeys=0`
- 품질은 "baseline 대비"로만 회귀 차단: `hit@5 -5pp`, `hit@10 -3pp`, `MRR -0.05`, `noResult +5pp`
- 절대 바닥값은 낮게: `hit@5 ≥ 0.60`, `hit@10 ≥ 0.75`, `noResult ≤ 0.20`
- 성능은 상한만(대형 회귀 차단): `p95 ≤ max(1.5x, +100ms) & ≤500ms`, `p99 ≤ max(2x, +200ms) & ≤1000ms`

원칙: **"과도하게 빡세지 않게(=회귀만 잡는 수준)"**이고, 결정성/프라이버시/Network 0을 최우선으로 둠.

---

### P1-2: 출처 UX 강화 (안전한 스니펫, 원문 과다 노출 금지)
**DoD:**
- subject + 짧은 스니펫만 표시
- 본문 전체 노출 금지 유지

**Gate:**
- `scripts/verify_telemetry_rag_meta_only.sh`에 "출처/스니펫 관련 금지키" 검증 유지

### P1-3: IndexedDB 버전업/마이그레이션 전략 고정
**DoD:**
- v1→v2 마이그레이션 또는 clear/rebuild 정책 문서+코드 고정
- 실패 시 UX 멈춤 없음

### P1-4: 성능 KPI 고도화 (meta-only)
**DoD:**
- `ragEmbeddingMs`/`ragRetrieveMs`/`ragIndexHydrateMs` 추가 (숫자/불리언/enum만)
- 원문 키 0 보장

## 실행 원칙
- 스크립트로 고정 (수동 절차 금지)
- 결정적 픽스처 + verify 스크립트 PASS 출력
- 증빙은 저장소에 남김 (PR 코멘트 또는 docs 커밋)

