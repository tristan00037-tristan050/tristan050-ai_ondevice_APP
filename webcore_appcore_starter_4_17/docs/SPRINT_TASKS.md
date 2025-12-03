# 다음 스프린트 태스크 구현 완료

이 문서는 다음 스프린트 태스크의 구현 내용을 설명합니다.

## ✅ 구현 완료 항목

### 1. Ajv 기반 풀 스키마 검증 (앱 런타임)

**파일**: `scripts/validateReportFull.js`

경량 검증(`validateReportLite`)을 Ajv 풀 검증으로 교체했습니다.

**기능**:
- Ajv를 사용한 완전한 JSON Schema 검증
- `ajv-formats`를 통한 날짜/시간 형식 검증
- 상세한 에러 메시지 출력
- CI/CD 파이프라인 통합 가능

**사용법**:
```bash
node scripts/validateReportFull.js <qc_report.json> [--schema <schema_path>]
```

**통합**:
- `scripts/validate_all.js`에 통합되어 정책 및 리포트 스키마를 모두 검증
- `package.json`의 `validate:report` 스크립트로 실행 가능

### 2. 레드랙션 커버리지 측정

**파일**: `scripts/redactionCoverage.js`

수집 로그에 대한 마스킹 비율 산정 및 임계 미달 시 경고 기능을 구현했습니다.

**기능**:
- 레드랙션 규칙별 매칭 수 집계
- 전체 마스킹 비율 계산
- 과도 마스킹 가드(기본 80%) 검증
- 임계값 미달 시 경고
- 규칙별 상세 리포트 출력

**사용법**:
```bash
node scripts/redactionCoverage.js <log_file> --rules <redact_rules.json> [--threshold <pct>]
```

**출력 예시**:
```
📊 레드랙션 커버리지 리포트
============================================================
원본 크기: 1024 bytes
마스킹된 문자 수: 256 bytes
마스킹 비율: 25.00%
총 매칭 수: 5

규칙별 상세:
  ✅ Bearer/Token: 2개 매칭
  ✅ Internal hostnames: 1개 매칭
  ✅ IPv4 addresses: 2개 매칭
```

### 3. OpenAPI 타입 자동 재생성 CI

**파일들**:
- `scripts/generate-types.sh` - 타입 생성 스크립트
- `scripts/check_openapi_sync.js` - 타입 동기화 검증
- `.github/workflows/openapi-types.yml` - GitHub Actions 워크플로우

**기능**:
- BFF/Collector OpenAPI 스펙에서 TypeScript 타입 자동 생성
- `openapi-typescript` 도구 사용
- PR마다 자동 타입 재생성 및 검증
- `git diff --exit-code`로 변경사항 감지
- 생성된 타입 파일의 TypeScript 구문 검증

**사용법**:
```bash
# 타입 생성
./scripts/generate-types.sh

# 타입 동기화 확인만 (CI용)
./scripts/generate-types.sh --check-only

# 타입 파일 검증
node scripts/check_openapi_sync.js
```

**CI 통합**:
- GitHub Actions 워크플로우가 PR 시 자동 실행
- OpenAPI 스펙 변경 시 타입 자동 재생성
- 타입 파일 변경이 있으면 CI 실패

## 📦 의존성

다음 npm 패키지가 필요합니다:

```json
{
  "devDependencies": {
    "ajv": "^8.12.0",
    "ajv-formats": "^2.1.1",
    "openapi-typescript": "^7.0.0"
  }
}
```

## 🔧 CI/CD 통합

### package.json 스크립트

```json
{
  "scripts": {
    "validate:report": "node scripts/validateReportFull.js",
    "validate:redaction": "node scripts/redactionCoverage.js",
    "ci:gen-types": "./scripts/generate-types.sh",
    "ci:check-openapi": "node scripts/check_openapi_sync.js",
    "ci": "npm run ci:gen-types && npm run ci:check-openapi"
  }
}
```

### GitHub Actions

`.github/workflows/openapi-types.yml`이 다음 시점에 자동 실행됩니다:
- Pull Request 생성/업데이트 시 (OpenAPI 스펙 변경 감지)
- 수동 트리거 (`workflow_dispatch`)

## 📝 참고사항

1. **타입 생성 경로**: 기본적으로 `packages/app-expo/src/types/generated/`에 타입 파일이 생성됩니다.
   - 환경 변수 `TYPES_DIR`로 변경 가능
   - `BFF_OPENAPI`, `COLLECTOR_OPENAPI`로 OpenAPI 스펙 경로 지정 가능

2. **레드랙션 커버리지**: 기본 임계값은 80%입니다.
   - `--threshold` 옵션으로 변경 가능
   - 규칙 파일의 `over_redaction_guard_pct` 설정도 확인

3. **스키마 검증**: `validate_all.js`는 정책과 리포트 스키마를 모두 검증합니다.
   - `--policy`, `--report` 옵션으로 파일 경로 지정 가능

## 🚀 다음 단계

이제 다음 작업을 진행할 수 있습니다:

1. 실제 모노레포 구조에 맞게 경로 조정
2. OpenAPI 스펙 파일 경로 확인 및 설정
3. CI/CD 파이프라인에 통합
4. 테스트 및 검증


