# 보안 감사 체크리스트

Phase 5.4 프로덕션 배포 전 보안 점검 항목입니다.

## 🔒 보안 점검 항목

### 1. 컨테이너 이미지 취약점 스캔

**도구**: Trivy

**실행 방법**:
```bash
# Trivy 설치
brew install trivy  # macOS
# 또는
wget https://github.com/aquasecurity/trivy/releases/download/v0.50.0/trivy_0.50.0_Linux-64bit.tar.gz
tar -xzf trivy_0.50.0_Linux-64bit.tar.gz
sudo mv trivy /usr/local/bin/

# 이미지 스캔
trivy image collector:5.4.0
trivy image bff:5.4.0
trivy image ops-console:5.4.0
```

**체크리스트**:
- [ ] Critical 취약점: 0개
- [ ] High 취약점: 0개 (또는 승인된 예외)
- [ ] Medium 취약점: 문서화 및 승인
- [ ] 스캔 결과 문서화

**승인 기준**:
- Critical/High 취약점이 있으면 배포 중단
- Medium 취약점은 위험 평가 후 결정

---

### 2. 정적 코드 분석 (SAST)

**도구**: ESLint, TypeScript, SonarQube (선택사항)

**실행 방법**:
```bash
# ESLint 실행
npm run lint --workspaces

# TypeScript 타입 체크
npm run type-check --workspaces

# SonarQube (선택사항)
sonar-scanner
```

**체크리스트**:
- [ ] ESLint 오류: 0개
- [ ] TypeScript 오류: 0개
- [ ] 보안 관련 경고 검토
- [ ] 하드코딩된 비밀번호/키 없음
- [ ] SQL Injection 취약점 없음
- [ ] XSS 취약점 없음

**검사 항목**:
- 하드코딩된 자격 증명
- SQL Injection 가능성
- XSS 취약점
- 인증/인가 누락
- 민감 정보 로깅

---

### 3. 권한 및 역할 가드

**검사 항목**:
- [ ] 모든 `/admin/*` 엔드포인트에 `requireTenantAuth` 적용
- [ ] 모든 `/admin/*` 엔드포인트에 역할 가드 적용 (향후 구현)
- [ ] 테넌트 격리 보장 (모든 쿼리에 `tenant_id` 필터)
- [ ] API Key 검증 강제
- [ ] 서명 토큰 검증 강제

**검증 방법**:
```bash
# 역할 가드 CI 게이트 실행
node scripts/check_roles_guard.mjs

# 테넌트 격리 검증
# 모든 엔드포인트에서 다른 테넌트 데이터 접근 불가 확인
```

**체크리스트**:
- [ ] `/admin/audit/logs` - `requireTenantAuth` 적용
- [ ] `/admin/retention/run` - `requireTenantAuth` 적용
- [ ] `/reports/*` - 테넌트 격리 보장
- [ ] `/timeline` - 테넌트 격리 보장
- [ ] `/ingest/qc` - 테넌트 격리 보장

---

### 4. 입력 검증

**검사 항목**:
- [ ] SQL Injection 방지 (패턴 검사)
- [ ] XSS 방지 (패턴 검사)
- [ ] 입력 길이 제한
- [ ] 숫자 범위 검증
- [ ] ID 형식 검증

**검증 방법**:
```bash
# SQL Injection 시도
curl "http://localhost:9090/reports?id=1' OR '1'='1" \
  -H "X-Api-Key: collector-key" \
  -H "X-Tenant: default"
# 예상 응답: 400 Bad Request

# XSS 시도
curl "http://localhost:9090/reports?id=<script>alert('xss')</script>" \
  -H "X-Api-Key: collector-key" \
  -H "X-Tenant: default"
# 예상 응답: 400 Bad Request
```

**체크리스트**:
- [ ] SQL Injection 패턴 차단 확인
- [ ] XSS 패턴 차단 확인
- [ ] 입력 검증 미들웨어 적용 확인
- [ ] 에러 메시지에 민감 정보 노출 없음

---

### 5. 암호화 및 비밀 관리

**검사 항목**:
- [ ] API Key 비영구화 (AsyncStorage에 저장하지 않음)
- [ ] 암호화 키 환경 변수로 관리
- [ ] 데이터베이스 비밀번호 환경 변수로 관리
- [ ] 서명 시크릿 환경 변수로 관리
- [ ] 로그에 민감 정보 노출 없음

**검증 방법**:
```bash
# 환경 변수 확인
env | grep -E "API_|EXPORT_|ENCRYPTION_|DB_"
# 하드코딩된 값이 없어야 함

# 코드 스캔
grep -r "password.*=" packages/collector-node-ts/src
grep -r "api.*key.*=" packages/collector-node-ts/src
# 하드코딩된 자격 증명이 없어야 함
```

**체크리스트**:
- [ ] 하드코딩된 비밀번호/키 없음
- [ ] 환경 변수로 모든 비밀 관리
- [ ] Kubernetes Secret 사용
- [ ] 로그 마스킹 적용

---

### 6. 네트워크 보안

**검사 항목**:
- [ ] HTTPS 적용 (프로덕션)
- [ ] CORS 설정 적절
- [ ] Rate Limiting 적용
- [ ] 헬멧 미들웨어 적용

**검증 방법**:
```bash
# CORS 확인
curl -H "Origin: https://evil.com" http://collector.production/reports
# 예상: CORS 에러 또는 차단

# Rate Limiting 확인
for i in {1..150}; do
  curl http://collector.production/reports \
    -H "X-Api-Key: collector-key" \
    -H "X-Tenant: default"
done
# 예상: 429 Too Many Requests
```

**체크리스트**:
- [ ] HTTPS 강제 (프로덕션)
- [ ] CORS 허용 도메인 제한
- [ ] Rate Limiting 동작 확인
- [ ] 보안 헤더 설정 확인

---

### 7. 감사 로그

**검사 항목**:
- [ ] 모든 API 요청 로깅
- [ ] 보안 이벤트 자동 감지
- [ ] 감사 로그 접근 제어
- [ ] 로그 보존 정책

**검증 방법**:
```bash
# 감사 로그 조회
curl http://collector.production/admin/audit/logs \
  -H "X-Api-Key: collector-key" \
  -H "X-Tenant: default"

# 보안 이벤트 확인
curl "http://collector.production/admin/audit/logs?security_event=true" \
  -H "X-Api-Key: collector-key" \
  -H "X-Tenant: default"
```

**체크리스트**:
- [ ] 모든 요청 로깅 확인
- [ ] 보안 이벤트 감지 확인
- [ ] 감사 로그 접근 제어 확인
- [ ] 로그 보존 정책 문서화

---

### 8. 데이터베이스 보안

**검사 항목**:
- [ ] 데이터베이스 접근 제어
- [ ] 테넌트 격리 보장
- [ ] SQL Injection 방지
- [ ] 백업 암호화

**검증 방법**:
```bash
# 데이터베이스 접근 제어 확인
psql -h $DB_HOST -U $DB_USER -d $DB_NAME -c "\du"
# 최소 권한 원칙 확인

# 테넌트 격리 확인
# 다른 테넌트 데이터 조회 불가 확인
```

**체크리스트**:
- [ ] 데이터베이스 사용자 최소 권한
- [ ] 테넌트 격리 쿼리 확인
- [ ] 파라미터화된 쿼리 사용
- [ ] 백업 파일 암호화

---

## 📋 보안 감사 체크리스트

### 사전 배포

- [ ] Trivy 스캔 통과
- [ ] SAST 검사 통과
- [ ] 역할 가드 검증 통과
- [ ] 입력 검증 검증 통과
- [ ] 암호화 및 비밀 관리 검증 통과
- [ ] 네트워크 보안 검증 통과
- [ ] 감사 로그 검증 통과
- [ ] 데이터베이스 보안 검증 통과

### 배포 후

- [ ] 프로덕션 환경 Trivy 스캔
- [ ] 네트워크 보안 설정 확인
- [ ] 감사 로그 수집 확인
- [ ] 알림 시스템 동작 확인

---

## 🚨 보안 이슈 발견 시

### Critical 이슈

- **조치**: 즉시 배포 중단
- **보고**: 보안팀에 즉시 보고
- **수정**: 이슈 해결 후 재검토

### High 이슈

- **조치**: 배포 보류
- **평가**: 위험 평가 후 결정
- **수정**: 이슈 해결 또는 승인된 예외

### Medium 이슈

- **조치**: 문서화 및 승인
- **수정**: 다음 릴리스에 포함

---

## 📚 참고 문서

- `docs/PHASE_5_4_SECURITY.md` - 보안 강화 가이드
- `scripts/check_roles_guard.mjs` - 역할 가드 CI 게이트
- `scripts/check_client_filter.mjs` - 클라이언트 필터 CI 게이트

---

**보안 감사 담당자**: 보안팀
**승인자**: 보안 리더
**감사 주기**: 배포 전 + 정기 (분기별)


