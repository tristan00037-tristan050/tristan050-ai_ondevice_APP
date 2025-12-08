# R7 Release Notes

## 개요

R7 릴리스는 **AI 온디바이스 회계 OS**의 핵심 기능을 완성하고, 파일럿 운영을 위한 기반을 마련한 주요 마일스톤입니다.

## 주요 기능

### 1. Risk Score Engine (R7-H)

고액 거래 및 리스크 필터링을 위한 Risk Score Engine v1을 도입했습니다.

- **Risk Level**: LOW, MEDIUM, HIGH 3단계 분류
- **Risk Factors**: HIGH_VALUE (>1M KRW), LOW_CONFIDENCE (<0.6), MEDIUM_VALUE (0.5-1M KRW)
- **자동 계산**: Suggest API 호출 시 자동으로 Risk Score 계산 및 저장

### 2. Manual Review Workbench (R7-H+1)

수동 검토 워크플로우를 완성했습니다.

- **Manual Review Queue**: PENDING → IN_REVIEW → APPROVED/REJECTED 상태 머신
- **HUD 통합**: HIGH Risk 거래에서 직접 수동 검토 요청 가능
- **Backoffice Workbench**: auditor 권한으로 큐 전체 조회 및 승인/거절 처리

### 3. On-Device Suggest Engine (R7-H+2)

온디바이스 Suggest 엔진 인터페이스를 도입했습니다.

- **엔진 추상화**: `SuggestEngine` 인터페이스로 local/remote 엔진 분리
- **로컬 엔진**: 규칙 기반 분류 (나중에 LLM으로 교체 가능)
- **엔진 출처 표시**: HUD에서 어떤 엔진이 추천을 생성했는지 명확히 표시

### 4. OS Dashboard (R7-H+2)

파일럿 전체 건강 상태를 한눈에 볼 수 있는 대시보드를 제공합니다.

- **파일럿 지표**: Top-1 정확도, Manual Review 비율
- **Risk 모니터링**: HIGH/MEDIUM/LOW Risk 분포
- **Health 메트릭**: BFF Success Rate, P95 지연 시간

### 5. Observability & Hardening (R7-H+3)

파일럿 운영을 위한 관측성과 안정성을 강화했습니다.

- **Health Check**: `/healthz`, `/readyz` 엔드포인트
- **에러 집계**: 4xx/5xx 에러율, 성공률 집계
- **Offline Queue Inspector**: HUD에서 대기 중인 큐 항목 확인
- **에러 UX 일원화**: 공통 에러 핸들러로 일관된 에러 표시
- **BFF 설정 검증**: Live 모드에서 BFF 연결 상태 자동 확인

## 기술 스택

- **Backend**: Node.js + Express.js (BFF)
- **Database**: PostgreSQL (audit, risk scores, manual review queue)
- **Frontend**: React Native (HUD), React + Vite (Backoffice)
- **Monorepo**: npm workspaces

## API 변경사항

### 신규 엔드포인트

- `GET /v1/accounting/risk/:posting_id` - Risk Score 조회
- `GET /v1/accounting/risk/high` - HIGH Risk 거래 목록 (페이지네이션 지원)
- `GET /v1/accounting/manual-review` - Manual Review 큐 조회 (페이지네이션 지원)
- `GET /v1/accounting/manual-review/:id` - Manual Review 상세 조회
- `POST /v1/accounting/manual-review/:id/resolve` - Manual Review 상태 변경
- `GET /v1/accounting/os/dashboard` - OS Dashboard 집계 데이터 (날짜 범위 파라미터 지원)
- `GET /healthz` - Health Check
- `GET /readyz` - Ready Check (DB 연결 포함)

### API 사용 예시

#### OS Dashboard (날짜 범위 지정)

```bash
# 기본값: 지난 7일
curl -H "X-Tenant: default" \
     -H "X-User-Role: auditor" \
     -H "X-User-Id: admin-1" \
     http://localhost:8081/v1/accounting/os/dashboard

# 특정 기간 지정
curl -H "X-Tenant: default" \
     -H "X-User-Role: auditor" \
     -H "X-User-Id: admin-1" \
     "http://localhost:8081/v1/accounting/os/dashboard?from=2025-12-01&to=2025-12-07&tenant=default"
```

#### 리포트 스크립트와 동일한 기간으로 조회

```bash
# 리포트 스크립트 실행
npm run report:pilot -- --from 2025-12-01 --to 2025-12-07 --tenant default

# Dashboard API로 동일 기간 조회
curl "http://localhost:8081/v1/accounting/os/dashboard?from=2025-12-01&to=2025-12-07&tenant=default" \
     -H "X-Tenant: default" \
     -H "X-User-Role: auditor" \
     -H "X-User-Id: admin-1"
```

#### Risk API (페이지네이션)

```bash
# 첫 페이지 (기본값: page=1, page_size=50)
curl -H "X-Tenant: default" \
     -H "X-User-Role: operator" \
     "http://localhost:8081/v1/accounting/risk/high?page=1&page_size=50"

# 다음 페이지
curl -H "X-Tenant: default" \
     -H "X-User-Role: operator" \
     "http://localhost:8081/v1/accounting/risk/high?page=2&page_size=50"
```

#### Manual Review API

```bash
# PENDING 상태 항목만 조회
curl -H "X-Tenant: default" \
     -H "X-User-Role: operator" \
     "http://localhost:8081/v1/accounting/manual-review?status=PENDING"

# 상태 변경 (승인)
curl -X POST \
     -H "X-Tenant: default" \
     -H "X-User-Role: auditor" \
     -H "X-User-Id: admin-1" \
     -H "Content-Type: application/json" \
     -d '{"status": "APPROVED", "note": "승인 완료"}' \
     "http://localhost:8081/v1/accounting/manual-review/1/resolve"
```

### 데이터베이스 스키마

- `accounting_risk_scores` - Risk Score 저장
- `accounting_manual_review_queue` - Manual Review 큐
- 집계 뷰: `accounting_os_pilot_summary`, `accounting_os_risk_summary`, `accounting_os_health_summary`

## 마이그레이션 가이드

```bash
# 1. DB 마이그레이션 실행
export DATABASE_URL="postgres://app:app@localhost:5432/app"
npm run db:migrate

# 2. BFF 서버 재빌드
docker compose up -d --build bff

# 3. 테스트
npm run demo:app:mock  # Mock 모드
npm run demo:app:live  # Live 모드
npm run demo:web      # Backoffice
```

## 알려진 이슈

- Mock 모드에서는 실제 네트워크 호출이 발생하지 않습니다.
- Offline Queue는 localStorage 기반으로 동작합니다 (브라우저 환경).
- Health 집계는 audit_events 기반으로 추정치를 제공합니다 (실제 access log 테이블 필요).

## 다음 단계 (R8)

- 실제 온디바이스 LLM 통합
- Access Log 테이블 및 상세 메트릭 수집
- Prometheus/Grafana 통합
- CI/CD 파이프라인 강화

## 참고 문서

- [POC Playbook](./POC_PLAYBOOK.md) - 외부 PoC 시연 가이드
- [Technical Debt](./TECH_DEBT.md) - 기술 부채 문서

