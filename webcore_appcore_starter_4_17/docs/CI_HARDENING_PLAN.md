# CI 강화 계획 (R8-S1)

## 📋 현재 CI 상태 요약

### 현재 구조

- **build job 제거**: 빌드 단계가 CI 파이프라인에서 제거됨
- **test job 의존성**: `needs: [lint-and-typecheck, schema-validation]`로 설정
- **Non-blocking 체크**:
  - ESLint: `continue-on-error: true` (service-core-accounting, bff-accounting, ops-console)
  - TypeScript: `continue-on-error: true` (service-core-accounting, bff-accounting)
  - OpenAPI sync: `continue-on-error: true`
  - Schema validation: 일부 경고만 출력

### 현재 문제점

1. **타입 안정성 부족**: TypeScript 오류가 있어도 CI가 통과됨
2. **코드 품질 게이트 부재**: ESLint 경고가 있어도 CI가 통과됨
3. **ops-console TypeScript 설정**: 일부 strict 옵션이 완화됨
4. **app-expo type-check**: CI에 편입되지 않음

## 🎯 R8-S1 목표

### 1. 핵심 패키지 게이트 복원

- `@appcore/service-core-accounting`
- `@appcore/bff-accounting`

위 두 패키지에 대해:
- ESLint를 blocking gate로 복원
- TypeScript type-check를 blocking gate로 복원

### 2. ops-console TypeScript 옵션 재강화

- `noUnusedLocals: true` 복원
- `noUnusedParameters: true` 복원
- React Router 타입 호환성 문제 해결

### 3. app-expo type-check CI 편입

- `app-expo` 패키지의 type-check 스크립트를 CI에 추가
- 초기에는 non-blocking으로 시작, 점진적으로 blocking 전환

## 📊 단계적 플랜

### Phase 1: 경고 수 집계/리포트 (Non-blocking 유지)

**목표**: 현재 상태를 유지하면서 경고 수를 추적

- ESLint 경고 수를 집계하여 리포트 출력
- TypeScript 오류 수를 집계하여 리포트 출력
- CI 아티팩트로 경고 리포트 저장
- **기간**: R8-S1 시작 ~ 2주

**작업**:
- CI job에 경고 수 집계 스크립트 추가
- GitHub Actions summary에 경고 수 표시

### Phase 2: 핵심 패키지 Blocking 전환

**목표**: service-core-accounting, bff-accounting만 blocking gate로 전환

- ESLint: `continue-on-error: false` (핵심 패키지만)
- TypeScript: `continue-on-error: false` (핵심 패키지만)
- ops-console, app-expo는 Phase 1 유지
- **기간**: Phase 1 완료 후 ~ 2주

**작업**:
- 핵심 패키지의 모든 ESLint/TS 오류 수정
- CI job에서 핵심 패키지만 blocking으로 설정
- 다른 패키지는 계속 non-blocking 유지

### Phase 3: ops-console / app-expo 확장

**목표**: 모든 패키지에 blocking gate 적용

- ops-console TypeScript 설정 재강화
- app-expo type-check CI 편입 및 blocking 전환
- **기간**: Phase 2 완료 후 ~ 2주

**작업**:
- ops-console의 React Router 타입 문제 해결
- app-expo type-check 스크립트 추가 및 CI 편입
- 모든 패키지의 ESLint/TS 오류 수정

## 🔍 세부 작업 항목

### Phase 1 작업

- [ ] CI job에 경고 집계 스크립트 추가
- [ ] GitHub Actions summary에 경고 수 표시
- [ ] 경고 리포트 아티팩트 저장

### Phase 2 작업

- [ ] `@appcore/service-core-accounting` ESLint 오류 수정
- [ ] `@appcore/service-core-accounting` TypeScript 오류 수정
- [ ] `@appcore/bff-accounting` ESLint 오류 수정
- [ ] `@appcore/bff-accounting` TypeScript 오류 수정
- [ ] CI job에서 핵심 패키지만 blocking으로 전환

### Phase 3 작업

- [ ] ops-console React Router 타입 문제 해결
- [ ] ops-console TypeScript strict 옵션 복원
- [ ] app-expo type-check 스크립트 추가
- [ ] app-expo type-check CI 편입
- [ ] 모든 패키지 ESLint/TS 오류 수정

## 📝 성공 기준

### Phase 1 성공 기준

- 경고 수가 CI summary에 표시됨
- 경고 리포트가 아티팩트로 저장됨
- 기존 CI 파이프라인이 정상 작동

### Phase 2 성공 기준

- `@appcore/service-core-accounting` ESLint/TS 오류 0개
- `@appcore/bff-accounting` ESLint/TS 오류 0개
- 핵심 패키지의 오류 시 CI 실패

### Phase 3 성공 기준

- 모든 패키지 ESLint/TS 오류 0개
- 모든 패키지의 오류 시 CI 실패
- CI 파이프라인 안정성 유지

## 🚨 리스크 관리

### 잠재적 리스크

1. **기존 코드 수정 범위**: Phase 2에서 많은 오류 수정 필요
2. **CI 파이프라인 안정성**: blocking 전환 시 CI 실패 가능
3. **개발 속도 저하**: strict 체크로 인한 개발 속도 저하

### 완화 방안

1. **점진적 전환**: 한 번에 모든 패키지를 전환하지 않고 단계적으로 진행
2. **Non-blocking 유지**: Phase 1에서 충분한 데이터 수집 후 전환
3. **팀 협의**: 각 Phase 전환 전 팀과 논의하여 일정 조정

## 📅 예상 일정

- **Phase 1**: R8-S1 시작 ~ 2주
- **Phase 2**: Phase 1 완료 후 ~ 2주
- **Phase 3**: Phase 2 완료 후 ~ 2주

**총 예상 기간**: 약 6주

## 📚 참고 문서

- [TypeScript Strict Mode](https://www.typescriptlang.org/tsconfig#strict)
- [ESLint Rules](https://eslint.org/docs/latest/rules/)
- [GitHub Actions Workflow Syntax](https://docs.github.com/en/actions/using-workflows/workflow-syntax-for-github-actions)

---

**이 문서는 개발팀/검토팀 CI 논의의 기준선으로 사용합니다.**



