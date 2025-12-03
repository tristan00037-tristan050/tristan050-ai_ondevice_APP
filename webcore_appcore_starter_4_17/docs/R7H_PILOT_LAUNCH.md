# R7-H 파일럿 운영 착수 가이드

## 개요

R7-H 파일럿 운영이 공식 승인되어 착수합니다. 파일럿 테넌트만 접근 가능하도록 게이팅이 적용되었습니다.

## 배포 정보

- **태그**: `r7-h-pilot-20251203`
- **주요 변경사항**:
  - 파일럿 테넌트 게이팅 (OS_TENANT_ALLOWLIST_JSON)
  - 리스크 스코어 엔진 인터페이스
  - 멀티테넌트 온보딩 템플릿 및 스크립트
  - BFF 안정화 (Ajv strict 모드 해제)

## 배포 절차

### 1. 태그 푸시

```bash
git push origin r7-h-pilot-20251203
```

GitHub Actions 릴리스 파이프라인이 자동으로 트리거됩니다:
- Docker Build
- GHCR Publish
- Helm Upgrade
- Post-deploy 스모크

### 2. Helm Values 설정 적용

#### 방법 1: Helm upgrade 시 직접 설정 (권장)

```bash
helm upgrade --install bff charts/bff-accounting \
  --set env.OS_TENANT_ALLOWLIST_JSON='["default","pilot-a"]' \
  --set image.tag=r7-h-pilot-20251203 \
  --namespace accounting
```

#### 방법 2: values.yaml 파일 수정

```yaml
env:
  OS_TENANT_ALLOWLIST_JSON: '["default","pilot-a"]'
```

그 후:
```bash
helm upgrade --install bff charts/bff-accounting \
  --namespace accounting
```

### 3. 파일럿 테넌트 온보딩

```bash
node scripts/onboard_tenant.mjs \
  --tenant=pilot-a \
  --template=contracts/tenant_template.default.json
```

온보딩 결과:
- 계정 매핑 설정
- 카테고리 목록
- 정책 기본값
- 어댑터 설정

**다음 단계** (수동):
1. Kubernetes Secret 생성 (어댑터 토큰 등)
2. 네트워크 정책 적용 (egress allow-list)

### 4. 모니터링 및 검증

#### 파일럿 테넌트 접근 확인 (성공 예상)

```bash
# 파일럿 테넌트 (허용)
curl -H 'X-Tenant: default' \
     -H 'X-User-Role: operator' \
     -H 'X-User-Id: pilot-user' \
     http://localhost:8081/v1/accounting/audit

# 응답: 200 OK 또는 403 (role에 따라)
```

```bash
# 파일럿 테넌트 (허용)
curl -H 'X-Tenant: pilot-a' \
     -H 'X-User-Role: operator' \
     -H 'X-User-Id: pilot-user' \
     http://localhost:8081/v1/accounting/audit

# 응답: 200 OK 또는 403 (role에 따라)
```

#### 비파일럿 테넌트 차단 확인 (403 예상)

```bash
# 비파일럿 테넌트 (차단)
curl -H 'X-Tenant: pilot-b' \
     -H 'X-User-Role: operator' \
     -H 'X-User-Id: pilot-user' \
     http://localhost:8081/v1/accounting/audit

# 응답: 403 Forbidden
# {
#   "error_code": "TENANT_NOT_ENABLED",
#   "tenant": "pilot-b",
#   "message": "Tenant not enabled for pilot"
# }
```

#### 로그 확인

```bash
# BFF 로그에서 차단 이벤트 확인
kubectl logs -n accounting deployment/bff-accounting | grep TENANT_NOT_ENABLED

# 또는 감사 로그 확인
# (감사 로그는 차단된 요청도 기록할 수 있음)
```

#### Prometheus 메트릭 확인

```promql
# 파일럿 테넌트 요청 수
sum(rate(http_requests_total{job="bff-accounting"}[5m])) by (tenant)

# 차단된 요청 수 (403)
sum(rate(http_requests_total{job="bff-accounting",code="403"}[5m])) by (tenant)
```

## 운영 체크리스트

### 배포 전
- [ ] Helm values에 `OS_TENANT_ALLOWLIST_JSON` 설정 확인
- [ ] 파일럿 테넌트 목록 확인: `["default","pilot-a"]`
- [ ] 이미지 태그 확인: `r7-h-pilot-20251203`

### 배포 후
- [ ] 파일럿 테넌트 접근 성공 확인
- [ ] 비파일럿 테넌트 차단 확인 (403)
- [ ] 로그에서 `TENANT_NOT_ENABLED` 이벤트 확인
- [ ] Prometheus 메트릭 확인
- [ ] 헬스 체크 통과: `/health`, `/ready`

### 파일럿 온보딩
- [ ] `onboard_tenant.mjs` 실행 완료
- [ ] Kubernetes Secret 생성 (어댑터 토큰)
- [ ] 네트워크 정책 적용 (필요 시)

## 롤백 절차

문제 발생 시 이전 버전으로 롤백:

```bash
# 이전 태그로 롤백
./scripts/rollback.sh r7-final-20251203

# 또는 Helm 직접
helm upgrade --install bff charts/bff-accounting \
  --set image.tag=r7-final-20251203 \
  --namespace accounting
```

## 알려진 이슈

1. **스키마 로드 경고**: 스키마 파일 로드 실패는 경고일 뿐이며 서비스 실행을 막지 않습니다.
2. **환경변수 형식**: `OS_TENANT_ALLOWLIST_JSON`은 JSON 배열 문자열이어야 합니다 (예: `'["default","pilot-a"]'`).

## 다음 단계

1. **파일럿 운영 모니터링** (2~4주)
   - 일일 사용량 추적
   - 오류/수동 검토/미매칭 데이터 수집
   - 대시보드 구축

2. **피드백 수집**
   - Backoffice 수동 검토 큐 모니터링
   - 운영 Slack/이슈 트래커 연동

3. **R8 준비**
   - 골든셋 확대 (≥100~200건)
   - 정확도 분석 스크립트 개선
   - 규칙/스코어 튜닝

## 참고 문서

- `docs/R7H_PILOT_GUIDE.md`: 파일럿 운영 가이드
- `docs/R8_PREP.md`: R8 준비 사항
- `docs/R7_FINAL_RELEASE_NOTES.md`: R7 릴리스 노트
- `scripts/set_pilot_tenants.sh`: 파일럿 테넌트 설정 스크립트
- `scripts/onboard_tenant.mjs`: 테넌트 온보딩 스크립트

