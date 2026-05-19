# D-4 Card 2 Migration Equivalence

STATUS=NEEDS_REVIEW

Base SHA: 25513bf6174d2bed0158e7d2d4a09e70fd678f33
PR #744 previous head: c6d0f65bea1f36d046248a6a507ecc080b38fc01

## Decision — 시나리오 X (실제 빌드 패키지: butler-desktop)

`butler-desktop/` 가 실제 production Tauri 빌드 패키지이므로, v1.1 컴포넌트를
`apps/butler-tauri/` 가 아닌 **`butler-desktop/src/components/v1_1/`** 로 통합한다.
`apps/butler-tauri/` 의 컴포넌트는 계약 원본(reference)으로 유지한다.

## Codex P1 — sidecar `/api/document_transform/*` 5종 alias 등록

| step | method | path | timeout | 처리 본질 |
|---|---|---|---|---|
| extract | POST | /api/document_transform/extract | 60s | legacy `_build_transform_response` 코어 동등 |
| parse_template | POST | /api/document_transform/parse_template | 60s | 동상 |
| map | POST | /api/document_transform/map | 60s | 동상 |
| compose | POST | /api/document_transform/compose | 60s | 동상 |
| stream | GET | /api/document_transform/stream | 180s + idle 30s | SSE — result_id 로 변환 결과 스트림 |

- legacy `POST /document_transform/transform_stream` 의 핸들러 본문을 공용 코어
  `_build_transform_response(form)` 로 추출 — 5종 alias 와 legacy 가 **동일 코어**
  를 호출(동등성 보장).
- legacy route 응답에 deprecation 헤더 부착:
  `X-Butler-Deprecated: true` / `X-Butler-Alternative: /api/document_transform/stream`.
- 4종 POST alias 는 multipart 입력 시 legacy transform 과 동등 처리, contract
  probe(입력 없음) 시 200 + endpoint descriptor(`api_contract_v1_1.endpoint_matrix`)
  반환 → `sidecar_endpoint_ping.log` 5종 전부 200 OK.
- timeout 값은 `butler_pc_core/document_transform/api_contract_v1_1.py` 계약에
  명시(extract/parse/map/compose 60s, stream 180s) — 본 hotfix 는 라우트 등록 범위.

## Codex P2 — v1.1 컴포넌트 실제 빌드(butler-desktop) 통합

신·구 컴포넌트 동등성:

| 영역 | 구(deprecated) | 신(v1.1) | 동등성 |
|---|---|---|---|
| 8-카드 그리드 | `chat/EmptyState.tsx` | `v1_1/CardGrid.tsx` | `onCardSelect(mode)` 시그니처 동일, 카드 8종 |
| 카드2 모달 | `chat/DocumentTransformModal.tsx` | `v1_1/Card2DocumentTransform.tsx` | `onClose` prop 동일, 외부/양식 dual upload + 4-step + 3-pane 결과 |
| 카드2 결과 | (모달 내장) | `v1_1/Card2Result.tsx` | 외부요약·매핑·우리결과 3-pane + .docx/.md 다운로드 |

- `App.tsx`: `EmptyState` → `CardGrid`, `DocumentTransformModal` → `Card2DocumentTransform`
  로 렌더링 교체. import 정합.
- `CardGrid.tsx` 의 `Icon` 타입을 butler-desktop lucide-react 버전에 맞춰
  `LucideIcon` 으로 정합 (apps/butler-tauri 원본의 narrow type 은 빌드 불통).
- 구 컴포넌트 2종(`EmptyState.tsx` / `DocumentTransformModal.tsx`)에 `@deprecated`
  JSDoc 표시 부착. 파일 자체는 **유지** — 기존 테스트 4종
  (`D3Card1Integration` / `EmptyState` / `D4Card2SidecarRetry` /
  `D4Card2DocumentTransform`)이 import 하므로 즉시 삭제 시 `tsc` 불통.

## 정직 보고 — 잔존 항목 (P3~P11 잔여 큐 영역)

- `grep -R "EmptyState|DocumentTransformModal" butler-desktop/src` 는 0건이 아니다:
  (a) 구 컴포넌트 파일 2종(@deprecated 표시), (b) 테스트 4종의 import,
  (c) `App.tsx` 의 state 변수명 `documentTransformModalOpen`(컴포넌트 아님),
  (d) `RequestParsingModal.tsx` 의 주석 1건. **컴포넌트 렌더링 사용은 0건.**
  테스트 4종 마이그레이션은 본 hotfix scope(P1/P2) 외 — P3~P11 잔여 큐에서 처리 권고.
- `no_emoji_grep.log`: 신규 v1.1 컴포넌트 이모지 0건. 기존 src/ 18건은 사전 존재분
  (P1/P2 무관) — 임의 확장 금지 정합상 미수정.
- GUI 스크린샷 / Playwright E2E: 미수행 (P3~P11 영역).

## Phase 3 — Deletion (차단 유지)

다음은 GUI T1~T5 PASS + 테스트 마이그레이션 전까지 삭제 금지:
- `butler-desktop/src/components/chat/DocumentTransformModal.tsx`
- `butler-desktop/src/components/chat/EmptyState.tsx`
- legacy `/document_transform/*` routes
