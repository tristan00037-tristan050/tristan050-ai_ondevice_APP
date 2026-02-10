1) 단일 앵커(절대 기준)
- bash scripts/verify/verify_repo_contracts.sh ; echo "EXIT=$?" -> EXIT=0

2) 신규 DoD 키(추가만, 기존 키 변경/삭제 0)
- OPS_HUB_TRACE_DB_SCHEMA_OK=1
- OPS_HUB_TRACE_REQUEST_ID_INDEX_OK=1
- OPS_HUB_TRACE_IDEMPOTENT_UPSERT_OK=1
- OPS_HUB_TRACE_CONCURRENCY_SAFE_OK=1
- OPS_HUB_TRACE_EVENT_SCHEMA_V1_OK=1

3) negative-first 포함(저장 전 차단, meta-only)
- 금지 키 포함 payload -> 저장 0(FAIL-CLOSED)

4) 외부 호출 0 증빙
- verify/테스트 경로에서 설치/다운로드/네트워크 동작 0 (판정만)

5) 원문/원문조각 0 증빙(로그/예외/리포트 포함)
- 저장 전 meta-only 검증 적용, 실패 시 reason_code 중심(원문 미출력)

6) 보조 컴퓨트 기본 OFF 증빙(우회 0)
- 보조 경로 우회 0, 기본 규율 영향 없음

추가 요약(meta-only)
- DB 기본값: sql.js (네이티브 better-sqlite3 기본값 금지)
- 멱등: event_id DB UNIQUE/PK로 강제
- 동시성 검증: Promise.all 동시 ingest 케이스 포함(순차 인정 불가)
- 접근 잠금: 로컬-only 또는 인증 필수, X-Api-Key 값 매칭(존재만 통과 금지), IPv6/::ffff 케이스 포함

검증 커맨드
- bash scripts/verify/verify_ops_hub_trace_db_store.sh ; echo "EXIT=$?" -> EXIT=0
- bash scripts/verify/verify_repo_contracts.sh ; echo "EXIT=$?" -> EXIT=0

관련 커밋
- 286f4051ef21bd5d0e733f0b91b69dbf02423467
