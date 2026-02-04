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

