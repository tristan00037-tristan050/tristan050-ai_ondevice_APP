# R10-S5 P1-3: IndexedDB v1→v2 마이그레이션 전략

## 정책 (운영/안정성 우선, 결정성 유지)

### 기본: Atomic Upgrade 시도

1. `indexedDB.open(name, 2)`의 `upgrade` 트랜잭션에서 schema 변경 + (가능하면) 데이터 이행
2. upgrade 중 실패하면 트랜잭션이 롤백되어야 함 (부분 이행 금지)

### 실패 시: Destructive Fallback = clear/rebuild

1. DB를 닫고 `indexedDB.deleteDatabase(name)` 후
2. `hydrateOrBuildIndex`가 "rebuild 경로"로 재생성

**원칙**: "데이터 일부가 깨진 채 남는 것"이 최악입니다. 실패 시 깨끗하게 삭제하고 재생성이 더 안전합니다 (UX 무중단에 유리).

## Schema 변경 사항

### v1 → v2 변경
- **DB_VERSION**: 1 → 2
- **Schema 변경**: 없음 (호환성 유지)
- **데이터 이행**: 기존 데이터 유지 (마이그레이션 불필요)
- **목적**: 버전 관리 및 향후 확장 대비

## 실패 처리

### Upgrade 실패 시
1. 트랜잭션 자동 롤백 (IndexedDB 기본 동작)
2. `upgrade` 이벤트에서 예외 발생 시 → `onerror` 핸들러에서 `deleteDatabase` 호출
3. 재초기화 시 `restore()` 실패 → `clear()` → `rebuild` 경로로 자동 전환

### 복원 실패 시
1. `restore()` 반환값이 `false`이면 → `clear()` 호출
2. `hydrateOrBuildIndex`에서 `hydrated=false` 반환
3. `buildIndex` 경로로 재생성

## UX 무중단 보장

- 모든 마이그레이션/복원 실패는 예외로 앱을 멈추지 않음
- 실패 시 자동으로 `clear/rebuild` 경로로 전환
- 사용자는 "인덱스 생성 중..." 메시지만 보게 됨 (Warm start 실패해도 Cold start로 자동 전환)

## 증빙 규칙

- 마이그레이션 스크립트 실행 로그: `docs/ops/r10-s5-p1-3-idb-migration-proof-*.log`
- 최신 증빙 포인터: `docs/ops/r10-s5-p1-3-idb-migration-proof.latest`

