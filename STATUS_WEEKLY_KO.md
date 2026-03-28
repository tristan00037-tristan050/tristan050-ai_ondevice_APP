# STATUS_WEEKLY_KO

기준일: 2026-03-28

## 전체 완성도
**78%**

| 항목 | 진행률 | 메모 |
|---|---:|---|
| 수집기(6포맷, SHA-256 dedup) | 90% | PDF/DOCX/TXT/JSONL/JSON/CSV 동작 |
| 정제기(PII/한국어/NFC) | 88% | regex 기반 5종 마스킹 |
| 품질 필터(도메인/중복/hallucination) | 84% | 규제 도메인 엄격 reject 포함 |
| 포맷 변환(JSONL/digest) | 92% | training record 생성 완료 |
| split/leakage | 86% | digest 그룹 단위 분할 |
| orchestrator/manifest/quarantine | 82% | dry-run/real-run 분리 완료 |
| 검증/pytest/로그 | 95% | dry-run + pytest 로그 포함 |
| 실데이터 운영 검증 | 20% | 운영팀 범위 |
| 스캔 PDF OCR lane | 15% | 후속 구현 필요 |
| 대규모 분산 dedup | 10% | DataTrove/MinHash 후속 |

## 이번 주 완료
- AI-23 필수 10개 파일 구현
- pytest 추가
- dry-run 검증 로그 생성
- README / PR 템플릿 / 벤치마킹 문서 작성

## 다음 주 우선순위
1. Presidio optional backend
2. Docling optional parser
3. real-run manifest/quarantine 운영 가이드
4. parquet export
5. restricted domain tuning
