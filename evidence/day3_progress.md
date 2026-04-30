# Day 3 진행 증거 — 2026-04-30

## 완료 현황

| 작업 | 상태 | 커밋 |
|------|------|------|
| Task 1: card_05 정확도 게이트 | ✅ 완료 | `0adc3d04` |
| Task 2: Personal Pack 검색 v2 | ✅ 완료 | `9e9465ac` |
| Task 3: 파일 유형별 청커 7종 | ✅ 완료 | `d4bf160a` |
| Task 4: 계정과목 사전 10→30 확장 | ✅ 완료 | `0adc3d04` |

---

## Task 1: card_05 정확도 게이트

### 구현 파일
- `scripts/eval/card05_accuracy.py` — 키워드 분류기 + 게이트 측정
- `tests/fixtures/card05_bank_samples/synthetic_100.jsonl` — PII-free 합성 100건
- `tests/test_card05_accuracy_gate.py` — 5케이스

### 게이트 결과
```
overall_accuracy : 98.0%  (PASS ≥ 90%)
per_category min : 80.0%  (PASS ≥ 80%)
critical_violations: 0    (PASS = 0)
gate_all_pass    : True
```

### 분류기 개선 사항
- 공백 정규화 매칭: `kw_nospace in desc_nospace` — 한국어 복합어 대응
- 최장 키워드 우선 (`(score, longest_kw)` 튜플 정렬) — 구체적 분류 우선
- `이자수익` 공백 포함 키워드 추가 (`"이자 수익"`, `"예금 이자"` 등)
- `통신비` 키워드 12개 추가 (구독, 워크스페이스, 365, 플랜 등)
- `보험료` 특수화 (화재/책임/기업보험만, `보험` 단독 제거)

### 테스트 5케이스
```
test_happy_overall_90pct_pass            PASS
test_boundary_per_category_80pct         PASS
test_adv_no_critical_misclassification   PASS
test_adv_account_code_map_override       PASS
test_adv_empty_description_safe_handling PASS
```

---

## Task 2: Personal Pack 하이브리드 검색 v2

### 구현 파일
- `butler_pc_core/retrieval/bm25_index.py` — Okapi BM25 (k1=1.5, b=0.75)
- `butler_pc_core/retrieval/vector_index.py` — TF-IDF 코사인 유사도
- `butler_pc_core/retrieval/rrf_fusion.py` — Reciprocal Rank Fusion (k=60)
- `butler_pc_core/retrieval/metadata_booster.py` — factpack(+0.05) + recency(+0.03)
- `butler_pc_core/retrieval/lightweight_reranker.py` — 키워드 겹침 기반 폴백
- `butler_pc_core/retrieval/pipeline.py` — HybridRetrievalPipeline

### 평가 결과
```
top-5 hit rate: 100% (30/30 queries)  [gate ≥ 90%]
```

### 테스트 8케이스
```
test_happy_top5_hit_rate_90pct             PASS  (실측 100%)
test_happy_metadata_boost_recent_file      PASS
test_boundary_reranker_timeout_fallback    PASS  (timeout=0.0s 폴백)
test_boundary_empty_query_handling         PASS
test_adv_factpack_priority_enforcement     PASS
test_adv_top5_hit_with_korean_query        PASS  (3개 한국어 쿼리)
test_adv_misspelled_filename_recovery      PASS
test_concurrent_two_queries_isolated       PASS  (threading)
```

---

## Task 3: 파일 유형별 청커 7종

### 구현 파일
- `butler_pc_core/retrieval/chunkers/base.py` — BaseChunker + Chunk 데이터클래스
- `butler_pc_core/retrieval/chunkers/meeting_minutes_chunker.py`
- `butler_pc_core/retrieval/chunkers/pdf_report_chunker.py`
- `butler_pc_core/retrieval/chunkers/docx_chunker.py`
- `butler_pc_core/retrieval/chunkers/xlsx_chunker.py`
- `butler_pc_core/retrieval/chunkers/email_chunker.py`
- `butler_pc_core/retrieval/chunkers/ppt_chunker.py`
- `butler_pc_core/retrieval/chunkers/receipt_chunker.py`
- `butler_pc_core/retrieval/chunkers/dispatcher.py`

### 청킹 정책 요약

| 유형 | 분할 경계 | 특이사항 |
|------|-----------|----------|
| 회의록 | 안건 헤더(##/번호/기호) | 초과 시 MAX_CHUNK_CHARS 재분할 |
| PDF 보고서 | 폼피드(\f) + 섹션 번호 헤더 | 페이지 번호 메타데이터 |
| DOCX | # 헤더 / HEADING: 태그 | 빈 줄 3개 이상 정규화 |
| XLSX | 시트 구분선 → ROWS_PER_CHUNK(30)행 | 헤더 행 각 청크 반복 |
| 이메일 | header/body/quoted 분리 | 스레드 구분선 재귀 처리 |
| PPT | 슬라이드 단위 (`=== Slide N ===`) | [Title] 추출 |
| 영수증 | 영수증 구분선 | 품목 20개씩 배치 |

### 테스트 22케이스 (21 공식 + 1 dispatcher)
```
MeetingMinutesChunker:  happy/boundary/adv   3 PASS
PdfReportChunker:       happy/boundary/adv   3 PASS
DocxChunker:            happy/boundary/adv   3 PASS
XlsxChunker:            happy/boundary/adv   3 PASS
EmailChunker:           happy/boundary/adv   3 PASS
PptChunker:             happy/boundary/adv   3 PASS
ReceiptChunker:         happy/boundary/adv   3 PASS
Dispatcher:             adv                  1 PASS
                                 합계:       22 PASS
```

---

## Task 4: 계정과목 사전 v2 (10→30개)

### 추가 항목 20개
상품매출, 상여금, 퇴직급여, 4대보험, 비품, 차량유지비, 도서인쇄비, 회의비,
보험료, 운반비, 수선비, 지급수수료, 세금과공과, 외주용역비, 교육훈련비,
여비교통비, 잡비, 이자수익, 기부금, 미분류

---

## 전체 회귀 테스트 결과
```
93 passed, 11 skipped (SSE — FastAPI 미설치 환경)
0 failed
```

## 누적 진행 (Day 1-3)
| 항목 | 수치 |
|------|------|
| 테스트 케이스 (Day 1~3) | 93+ passed |
| 카드 프롬프트 | 6종 완성 |
| 계정과목 사전 | 30개 |
| 청커 유형 | 7종 |
| 검색 파이프라인 | BM25+Vector+RRF+Boost+Rerank |
| card_05 정확도 | 98% (게이트 90%) |
| 검색 hit rate | 100% (게이트 90%) |
