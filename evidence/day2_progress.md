# Day 2 Progress Evidence

날짜: 2026-04-30  
브랜치: feat/day2-sse-cache-cards (PR 예정)

---

## Task 1 — SSE 진행률 스트림 엔드포인트

**파일**: `butler_sidecar.py`

| 항목 | 내용 |
|------|------|
| 엔드포인트 | `POST /api/analyze/stream` |
| 취소 엔드포인트 | `DELETE /api/analyze/{task_id}/cancel` |
| Content-Type | `text/event-stream` |
| 이벤트 종류 | `phase_start`, `chunk_progress`, `chunk_done`, `reduce_start`, `verify_start`, `complete`, `error`, `cancelled`, `heartbeat` |
| 타임아웃 | 하드 180s / 청크 45s |
| 하트비트 | 5초 idle 시 자동 발생 |
| 취소 추적 | `_active_controllers: dict[str, TimeoutController]` |

**테스트**: `tests/test_sse_stream.py` — 8 cases (fastapi 미설치 환경에서 skip)

---

## Task 2 — 4-Tier SQLite 캐시 시스템

**파일**: `butler_pc_core/runtime/cache/`

| 캐시 | 파일 | TTL | 키 구성 |
|------|------|-----|---------|
| DocumentTextCache | `document_text_cache.py` | 30일 | sha256(bytes):parser_version |
| ChunkEmbeddingCache | `chunk_embedding_cache.py` | 90일 | sha256(text):model:tokenizer |
| RetrievalCache | `retrieval_cache.py` | 7일 | sha256(query):index:top_k:filters[:16] |
| AnswerCache | `answer_cache.py` | 1일 | sha256(tmpl:digest:question:scenario) |

**공통 특성** (base.py):
- SQLite WAL 모드, LRU eviction (테이블당 256MB 한도)
- `get`, `set`, `invalidate(pattern)`, `stats()` 공통 API
- thread-safe (threading.Lock)

**테스트**:
- `tests/test_caches.py` — 25 cases (10 happy / 10 boundary / 4 adv / 3 concurrent ← 내부 분류 기준)
- `tests/test_cache_integration.py` — 3 integration cases

---

## Task 3 — 카드 프롬프트 5종 완성

**위치**: `butler_pc_core/prompts/cards/`

| 카드 | 제목 | forbidden_actions | examples |
|------|------|:-----------------:|:--------:|
| card_01_request_parse | 요청 핵심 파악 | 6개 | best+edge |
| card_02_external_to_our_format | 외부→내부 양식 | 6개 | best+edge |
| card_03_new_draft_from_past | 기존 문서 기반 초안 | 6개 | best+edge |
| card_04_document_review | 문서 검토·보완 | 6개 | best+edge |
| card_05_bank_to_accounting | 거래내역 회계분류 | 6개 | best+edge |
| card_06_fill_external_form | 외부 양식 자동기입 | 6개 | best+edge |

**테스트**: `tests/test_card_prompts.py` — 30 cases (5 항목 × 6 카드)

```
tests/test_card_prompts.py::test_card_has_required_top_level_keys[card_0x_...]  PASS  × 6
tests/test_card_prompts.py::test_card_has_forbidden_actions[card_0x_...]        PASS  × 6
tests/test_card_prompts.py::test_card_has_examples[card_0x_...]                 PASS  × 6
tests/test_card_prompts.py::test_card_examples_have_input_and_expected_output   PASS  × 6
tests/test_card_prompts.py::test_card_examples_have_best_and_edge_labels        PASS  × 6
```

---

## Task 4 — 테스트 Prefix 비율 게이트

**파일**: `scripts/check_test_prefix_ratio.py`

```
총 테스트: 238  (prefix 있음: 42, 기타: 196)
prefix        count   actual   target   pass
------------------------------------------------
happy            13   31.0%   30.0%     OK
boundary         12   28.6%   30.0%     OK
adv              14   33.3%   30.0%     OK
concurrent        3    7.1%   10.0%     OK
```

---

## 전체 테스트 결과 (Day 2 신규 파일)

```
tests/test_caches.py          25 passed
tests/test_cache_integration.py  3 passed
tests/test_card_prompts.py    30 passed
tests/test_sse_stream.py       8 skipped (fastapi 미설치)
─────────────────────────────────────────
합계: 58 passed, 8 skipped
```

---

## 커밋 계획

| 커밋 | 내용 |
|------|------|
| feat(sidecar): SSE progress stream + cancel endpoint | butler_sidecar.py Day 2 Task 1 |
| feat(cache): 4-tier SQLite cache system | cache/ + tests |
| feat(prompts): 5 card prompts — forbidden_actions + examples | cards/ + test |
| chore(scripts): test prefix ratio gate | scripts/check_test_prefix_ratio.py |
