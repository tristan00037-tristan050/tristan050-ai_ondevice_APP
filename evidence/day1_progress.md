# Butler PC Core Max v0.9 — Day 1 진행 증거

**날짜**: 2026-04-30  
**브랜치**: `feat/butler-pc-core-day1`  
**작성**: 자동 생성 (CI에서 갱신 예정)

---

## 완료 항목 체크리스트

| # | 항목 | 상태 | 파일 |
|---|------|------|------|
| 1 | 작업 등급 분류기 (5단계 Tier) | ✅ 완료 | `butler_pc_core/router/task_budget_router.py` |
| 2 | 분류기 테스트 (12+ 케이스) | ✅ 완료 (13 PASS) | `tests/butler_pc_core/test_task_budget_router.py` |
| 3 | `/api/precheck` 엔드포인트 | ✅ 완료 | `butler_sidecar.py` |
| 4 | Timeout/Cancel/Partial Result 컨트롤러 | ✅ 완료 | `butler_pc_core/runtime/timeout_controller.py` |
| 5 | 카드 6개 프롬프트 YAML | ✅ 완료 | `butler_pc_core/prompts/cards/` |
| 6 | Team Hub 페어링 JSON-RPC 스펙 | ✅ 완료 | `docs/team_hub/pairing_protocol.md` |

---

## 테스트 결과

```
tests/butler_pc_core/test_task_budget_router.py
  TestClassifyBytes::test_01_tier_s_exact_boundary     PASSED
  TestClassifyBytes::test_02_tier_s_small              PASSED
  TestClassifyBytes::test_03_tier_m_just_over_s        PASSED
  TestClassifyBytes::test_04_tier_m_boundary           PASSED
  TestClassifyBytes::test_05_tier_l_just_over_m        PASSED
  TestClassifyBytes::test_06_tier_l_boundary           PASSED
  TestClassifyBytes::test_07_tier_xl_just_over_l       PASSED  ← XL 차단 확인
  TestClassifyBytes::test_08_tier_xl_very_large        PASSED  ← XL 차단 확인
  TestClassifyBytes::test_09_media_image_png           PASSED
  TestClassifyBytes::test_10_media_audio_mp3           PASSED
  TestClassifyBytes::test_11_returns_budget_result_type PASSED
  TestClassifyFile::test_12_classify_real_file_tier_s  PASSED
  TestClassifyFile::test_file_not_found_raises         PASSED

13 passed in 0.02s
```

---

## 커밋 이력

| 커밋 | 메시지 |
|------|--------|
| e9ff67e8 | feat(butler-pc-core): task_budget_router — 5단계 작업 등급 분류기 + 13 테스트 |
| 6f3d4d01 | feat(butler-pc-core): /api/precheck 엔드포인트 추가 (butler_sidecar.py) |
| 1d32d36c | feat(butler-pc-core): TimeoutController — hard 180s / chunk 45s + partial_result.json |
| 88853016 | feat(butler-pc-core): 카드 6개 시나리오 프롬프트 YAML 초안 |
| a2fb315c | docs(team-hub): JSON-RPC 2.0 페어링 프로토콜 스펙 v1.0.0 |

---

## 파일 목록

```
butler_pc_core/
├── __init__.py
├── router/
│   ├── __init__.py
│   └── task_budget_router.py          ← Tier 분류기
├── runtime/
│   ├── __init__.py
│   └── timeout_controller.py         ← Timeout/Cancel/Partial
└── prompts/
    └── cards/
        ├── card_01_request_parse.yaml
        ├── card_02_external_to_our_format.yaml
        ├── card_03_new_draft_from_past.yaml
        ├── card_04_document_review.yaml
        ├── card_05_bank_to_accounting.yaml
        └── card_06_fill_external_form.yaml

butler_sidecar.py                      ← FastAPI / stdlib 사이드카

docs/team_hub/
└── pairing_protocol.md               ← JSON-RPC 2.0 스펙

tests/butler_pc_core/
├── conftest.py
└── test_task_budget_router.py        ← 13 테스트 케이스
```

---

## Day 2 예정

- [ ] 카드 실행 엔진 (card runner) 구현
- [ ] `/api/cards/{card_id}/run` 엔드포인트
- [ ] 카드별 입출력 JSON 스키마 검증기
- [ ] Team Hub 페어링 클라이언트 구현
- [ ] card_05 회계 분류 정확도 평가 데이터셋
