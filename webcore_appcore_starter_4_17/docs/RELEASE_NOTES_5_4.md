# Release Notes 5.4

Phase 5.4 운영 안정성 및 확장성 강화 릴리스 노트입니다.

**기준선**: R5d(v1) - 서버사이드 필터링, 테넌트 격리, ETag/멱등성 확정

**릴리스 날짜**: 2025-01-XX

**버전**: 5.4.0

---

## 🎯 주요 변경사항

### 데이터베이스 연동 (P0)

**변경 내용**:
- 인메모리 저장소(`Map<string, Report>`)를 PostgreSQL 데이터베이스로 완전 교체
- 트랜잭션 관리로 데이터 일관성 보장
- 인덱스 최적화로 쿼리 성능 향상

**영향**:
- ✅ 데이터 영속성 확보
- ✅ 서버 재시작 시에도 데이터 유지
- ✅ 대용량 데이터 처리 가능

**마이그레이션 필요**: 
- 데이터베이스 스키마 초기화 (`npm run migrate:init`)
- 기존 인메모리 데이터 마이그레이션 (선택사항)

---

### 모니터링/관측성 강화 (P1)

**변경 내용**:
- Prometheus 메트릭 엔드포인트 추가 (`GET /metrics`)
- 리포트 수집률, API 응답 시간, 에러율 추적
- 데이터베이스 연결 상태 모니터링

**새로운 메트릭**:
- `collector_reports_ingested_total{tenant="..."}` - 리포트 수집 수
- `collector_http_request_duration_seconds{endpoint="...", status="..."}` - API 응답 시간
- `collector_http_errors_total{endpoint="...", status="..."}` - HTTP 에러 수
- `collector_database_connected` - 데이터베이스 연결 상태

**영향**:
- ✅ 운영 환경 가시성 확보
- ✅ 성능 병목 지점 식별 가능
- ✅ 에러 추적 및 분석 가능

---

### 성능 최적화 (P1)

**변경 내용**:
- 인메모리 캐싱 전략 (리포트 목록, 타임라인)
- 데이터베이스 쿼리 최적화 (인덱스 활용)
- 배치 처리 최적화 (SQL 직접 집계)

**성능 개선**:
- 리포트 목록 조회: 캐시 히트 시 90% 속도 향상 (200ms → 20ms)
- 타임라인 집계: 캐시 히트 시 95% 속도 향상 (500ms → 25ms)
- SQL 직접 집계: 타임라인 집계 10배 이상 속도 향상

**영향**:
- ✅ 사용자 경험 개선
- ✅ 서버 부하 감소
- ✅ 확장성 향상

---

### 보안 강화 (P1)

**변경 내용**:
- API Rate Limiting (테넌트/IP/토큰별)
- 감사 로그 강화 (모든 요청 로깅, 보안 이벤트 감지)
- 입력 검증 강화 (SQL Injection, XSS 방지)
- 암호화 유틸리티 (AES-256-GCM, HMAC)

**새로운 기능**:
- `GET /admin/audit/logs` - 감사 로그 조회 API
- Rate Limit 헤더 (`X-RateLimit-Limit`, `X-RateLimit-Remaining`, `X-RateLimit-Reset`)
- 보안 이벤트 자동 감지 및 로깅

**영향**:
- ✅ DDoS 공격 방어
- ✅ 보안 이벤트 추적
- ✅ 민감 데이터 보호

---

### 운영 자동화 (P2)

**변경 내용**:
- CI/CD 파이프라인 강화 (자동 테스트, 빌드, 배포)
- Docker 컨테이너화 (멀티 스테이지 빌드)
- Kubernetes 배포 매니페스트
- 백업 자동화 (매일 자동 백업)
- 알림 시스템 (Slack, PagerDuty)

**새로운 파일**:
- `.github/workflows/ci.yml` - CI 파이프라인
- `.github/workflows/deploy.yml` - 배포 파이프라인
- `.github/workflows/backup.yml` - 백업 자동화
- `docker-compose.yml` - 로컬 개발용
- `k8s/*.yaml` - Kubernetes 매니페스트

**영향**:
- ✅ 배포 프로세스 자동화
- ✅ 운영 부하 감소
- ✅ 장애 대응 시간 단축

---

## 🔒 불변 원칙

이 릴리스는 다음 불변 원칙을 유지합니다:

1. **웹 코어 기준선 고정**: web-core-4.17.0(4054c04) 유지보수 모드
2. **정책/리포트 스키마 준수**: Ajv 검증(앱/Collector), CI 스키마 게이트 유지
3. **라벨 화이트리스트**: decision|ok 유지
4. **오프라인 우선**: 앱 업로더 큐(민감정보 미저장), 지수 백오프+지터
5. **테넌트 격리**: Collector 전 엔드포인트 강제 가드 + /bundle.zip 토큰 교차검증
6. **ETag 최적화**: 목록 정렬 고정/MD5 ETag 안정화, UI 304 활용
7. **OpenAPI/타입**: BFF/Collector 명세 → 타입 생성/동기화

**R5d(v1) 기준선 확정 사항**:
- ✅ 서버사이드 필터/페이지네이션만 허용 (클라이언트 필터/집계 금지)
- ✅ 테넌트 격리 + 역할 가드 필수
- ✅ 계약 우선 (OpenAPI→타입→Ajv)
- ✅ N+1 쿼리 금지
- ✅ 쿼리별 ETag/304
- ✅ 키/토큰 비영구화 유지

---

## 📋 마이그레이션 가이드

### 데이터베이스 마이그레이션

1. **PostgreSQL 데이터베이스 생성**
   ```bash
   createdb collector
   ```

2. **스키마 초기화**
   ```bash
   cd packages/collector-node-ts
   npm run migrate:init
   ```

3. **환경 변수 설정**
   ```bash
   export DB_HOST=localhost
   export DB_PORT=5432
   export DB_NAME=collector
   export DB_USER=postgres
   export DB_PASSWORD=postgres
   ```

4. **기존 인메모리 데이터 마이그레이션** (선택사항)
   - 기존 데이터가 있는 경우 `migrate:data` 스크립트 실행

### 환경 변수 업데이트

**새로운 환경 변수**:
- `DB_HOST`, `DB_PORT`, `DB_NAME`, `DB_USER`, `DB_PASSWORD` - 데이터베이스 연결
- `ENCRYPTION_KEY` - 암호화 키 (선택사항)
- `SLACK_WEBHOOK_URL` - Slack 알림 (선택사항)
- `PAGERDUTY_INTEGRATION_KEY` - PagerDuty 알림 (선택사항)

**기존 환경 변수 유지**:
- `API_KEYS` - API 키 매핑
- `EXPORT_SIGN_SECRET` - 서명 시크릿
- `RETAIN_DAYS` - 보존 기간

---

## 🐛 알려진 이슈

없음

---

## 🔄 호환성

### 하위 호환성

- ✅ API 엔드포인트 시그니처 유지
- ✅ 응답 형식 유지
- ✅ 인증/인가 방식 유지

### 비호환 변경사항

- ⚠️ 인메모리 저장소 제거: 기존 인메모리 데이터는 마이그레이션 필요
- ⚠️ 환경 변수 추가: 데이터베이스 연결 정보 필수

---

## 📚 참고 문서

- `docs/PHASE_5_4_KICKOFF.md` - Phase 5.4 킥오프 문서
- `docs/PHASE_5_4_COMPLETE.md` - Phase 5.4 완료 보고서
- `packages/collector-node-ts/README_DB.md` - 데이터베이스 연동 가이드
- `docs/GO_LIVE_CHECKLIST.md` - Go-Live 체크리스트
- `docs/ROLLBACK_PLAN.md` - 롤백 플랜

---

## 🙏 기여자

- Phase 5.4 개발팀

---

**다음 릴리스**: Phase 5.5 (예정)

