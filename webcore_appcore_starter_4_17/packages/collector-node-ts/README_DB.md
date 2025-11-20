# Collector 데이터베이스 연동 가이드

Phase 5.4 데이터베이스 연동 완료 문서입니다.

## 📋 개요

인메모리 저장소(`Map<string, Report>`)를 PostgreSQL 데이터베이스로 교체했습니다.

## 🗄️ 데이터베이스 스키마

### 테이블 구조

1. **reports** - 리포트 저장
   - `id` (VARCHAR, PK)
   - `tenant_id` (VARCHAR, NOT NULL)
   - `report_data` (JSONB, NOT NULL)
   - `markdown` (TEXT, NULL)
   - `created_at` (BIGINT, NOT NULL)
   - `updated_at` (BIGINT, NOT NULL)

2. **sign_history** - 서명 이력 (감사 로그)
   - `id` (SERIAL, PK)
   - `report_id` (VARCHAR, FK → reports.id)
   - `tenant_id` (VARCHAR, NOT NULL)
   - `requested_by` (VARCHAR, NOT NULL)
   - `token` (TEXT, NOT NULL)
   - `issued_at` (BIGINT, NOT NULL)
   - `expires_at` (BIGINT, NOT NULL)
   - `created_at` (BIGINT, NOT NULL)

3. **sign_token_cache** - 서명 토큰 캐시 (멱등성 보장)
   - `cache_key` (VARCHAR, PK)
   - `token` (TEXT, NOT NULL)
   - `expires_at` (BIGINT, NOT NULL)
   - `created_at` (BIGINT, NOT NULL)

### 인덱스

- `idx_reports_tenant_id` - 테넌트별 조회 최적화
- `idx_reports_created_at` - 시간순 정렬 최적화
- `idx_reports_tenant_created` - 복합 인덱스 (테넌트 + 시간)
- `idx_reports_policy_severity` - JSONB GIN 인덱스 (severity 필터링)
- `idx_reports_policy_version` - JSONB GIN 인덱스 (policy_version 필터링)

## 🚀 설정

### 환경 변수

```bash
# 데이터베이스 연결 정보
DB_HOST=localhost
DB_PORT=5432
DB_NAME=collector
DB_USER=postgres
DB_PASSWORD=postgres

# 기존 환경 변수 (유지)
API_KEYS="default:collector-key,teamA:teamA-key"
EXPORT_SIGN_SECRET=dev-secret
RETAIN_DAYS=30
```

### 데이터베이스 초기화

```bash
# 1. PostgreSQL 데이터베이스 생성
createdb collector

# 2. 스키마 초기화
cd packages/collector-node-ts
npm run migrate:init
```

## 📦 파일 구조

```
packages/collector-node-ts/src/db/
├── schema.sql              # 데이터베이스 스키마
├── client.ts               # PostgreSQL 클라이언트 (연결 풀)
├── reports.ts              # 리포트 레포지토리
├── signHistory.ts          # 서명 이력 레포지토리
├── signTokenCache.ts       # 토큰 캐시 레포지토리
└── migrate.ts              # 마이그레이션 스크립트
```

## 🔄 마이그레이션

### 스키마 초기화

```bash
npm run migrate:init
```

### 인메모리 데이터 마이그레이션 (레거시)

기존 인메모리 저장소에서 데이터베이스로 마이그레이션하는 경우:

```typescript
import { migrateFromMemory } from './db/migrate.js';
import { reports, signHistory, signTokenCache } from './routes/reports.js';

// 애플리케이션 시작 시 (한 번만 실행)
await migrateFromMemory(reports, signHistory, signTokenCache);
```

## 🧪 테스트

### 데이터베이스 연결 확인

```bash
# Health check 엔드포인트
curl http://localhost:9090/health

# 응답 예시
{
  "status": "ok",
  "service": "collector",
  "database": "connected"
}
```

### 리포트 저장/조회 테스트

```bash
# 리포트 인제스트
curl -X POST http://localhost:9090/ingest/qc \
  -H "X-Api-Key: collector-key" \
  -H "X-Tenant: default" \
  -H "Content-Type: application/json" \
  -d '{"status": {"api": "pass"}, "policy": {"policy_version": "v1"}}'

# 리포트 목록 조회
curl http://localhost:9090/reports \
  -H "X-Api-Key: collector-key" \
  -H "X-Tenant: default"
```

## 🔒 불변 원칙 유지

데이터베이스 연동 후에도 다음 불변 원칙을 유지합니다:

1. **테넌트 격리**: 모든 쿼리에 `tenant_id` 필터 적용
2. **ETag 최적화**: 정렬 고정으로 ETag 안정성 보장
3. **멱등성**: 서명 토큰 캐시로 멱등성 보장
4. **트랜잭션**: 리포트 저장 시 원자성 보장

## 📊 성능 최적화

### 인덱스 활용

- 테넌트별 조회: `idx_reports_tenant_id`
- 시간순 정렬: `idx_reports_created_at`
- 복합 필터: `idx_reports_tenant_created`
- JSONB 필터: `idx_reports_policy_severity`, `idx_reports_policy_version`

### 쿼리 최적화

- 서버 측 필터링으로 클라이언트 부하 감소
- 페이지네이션으로 대용량 데이터 처리
- JSONB 인덱스로 중첩 필드 검색 최적화

## 🐛 트러블슈팅

### 데이터베이스 연결 실패

```bash
# 연결 확인
psql -h localhost -U postgres -d collector

# 환경 변수 확인
echo $DB_HOST
echo $DB_NAME
```

### 스키마 초기화 실패

```bash
# 수동으로 스키마 실행
psql -h localhost -U postgres -d collector -f src/db/schema.sql
```

### 성능 이슈

```bash
# 인덱스 확인
psql -h localhost -U postgres -d collector -c "\d+ reports"

# 쿼리 실행 계획 분석
EXPLAIN ANALYZE SELECT * FROM reports WHERE tenant_id = 'default';
```

## 📚 참고 문서

- `docs/PHASE_5_4_KICKOFF.md` - Phase 5.4 킥오프 문서
- `src/db/schema.sql` - 데이터베이스 스키마
- `src/db/client.ts` - 데이터베이스 클라이언트

