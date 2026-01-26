# H3.4 Typecheck Gate SEALED Record

## Purpose

재발 방지 장치: TypeScript 타입 체크를 테스트 실행 전에 독립 단계로 강제하여, import 누락/타입 오류를 즉시 감지하고 명확한 오류 메시지를 제공합니다.

## Implementation

### Workflow Integration

- **File**: `.github/workflows/product-verify-model-registry.yml`
- **Step**: `Typecheck (fail-closed)`
- **Command**: `npm run typecheck` (in `webcore_appcore_starter_4_17/backend/model_registry`)
- **DoD Key**: `MODEL_REGISTRY_TYPECHECK_OK=1` (성공 시 출력)

### Typecheck Script

- **File**: `webcore_appcore_starter_4_17/backend/model_registry/package.json`
- **Script**: `"typecheck": "tsc -p tsconfig.json --noEmit --skipLibCheck"`
- **설정**:
  - `--noEmit`: 컴파일 출력 없이 타입 체크만 수행
  - `--skipLibCheck`: 외부 라이브러리 타입 정의 문제 무시 (우리 코드만 체크)
  - `-p tsconfig.json`: 프로젝트 tsconfig 기준으로 체크

## Evidence

### PR Link
- TBD (PR 생성 후 업데이트)

### Actions Run
- TBD (CI 실행 후 URL 업데이트)

### DoD Verification

```bash
# 로컬 검증
cd webcore_appcore_starter_4_17/backend/model_registry
npm run typecheck
echo "MODEL_REGISTRY_TYPECHECK_OK=1"

# CI에서 확인
# Typecheck (fail-closed) step 로그에 MODEL_REGISTRY_TYPECHECK_OK=1 출력 확인
```

## Benefits

1. **즉시 감지**: import 누락/타입 오류가 테스트 실행 전에 즉시 잡힘
2. **명확한 오류 메시지**: "테스트 실패"가 아닌 "타입체크 실패"로 명확
3. **재발 방지**: `getRegistryStore` 같은 import 누락을 사전에 차단
4. **운영 규율 준수**: 출력 기반 DoD 키로 증빙 가능

## Completion Checklist

- [x] `package.json`에 `typecheck` 스크립트 추가
- [x] 워크플로에 `Typecheck (fail-closed)` 단계 추가
- [x] DoD 키 `MODEL_REGISTRY_TYPECHECK_OK=1` 출력
- [x] `--skipLibCheck` 유지 (외부 라이브러리 타입 오류 무시)
- [x] SEALED 기록 문서 생성
- [ ] PR 링크 업데이트
- [ ] Actions run URL 업데이트

