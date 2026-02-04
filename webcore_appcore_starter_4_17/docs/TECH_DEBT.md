# 기술 부채 (Technical Debt)

이 문서는 프로젝트의 기술 부채를 추적하고 관리하기 위한 문서입니다.

## React Native 타입 호환성 문제

### 문제
`@types/react` 18과 `@types/react-native` 0.72 간의 타입 호환성 문제로 인해, React Native JSX 컴포넌트 사용 시 TS2786 오류가 발생합니다.

### 영향받는 파일
- `packages/app-expo/src/ui/AccountingHUD.tsx`
- `packages/app-expo/src/ui/components/ManualReviewButton.tsx`
- `packages/app-expo/src/ui/components/QueueBadge.tsx`
- `packages/app-expo/src/ui/components/RedactedText.tsx`
- `packages/app-expo/src/ui/hooks/useScreenPrivacy.tsx`
- `packages/app-expo/App.tsx`

### 해결 방법
해당 컴포넌트 사용 위치에 `@ts-expect-error` 주석을 추가하여 타입 체크를 우회합니다.

```typescript
// @ts-expect-error - React Native JSX type compatibility issue with @types/react 18
<View style={styles.container}>
```

### 향후 계획
- Expo SDK 업데이트 시 (`expo >= 50.0.0` → 최신 버전)
- `@types/react-native` 최신 버전으로 업그레이드 시
- 위 타입 호환성 문제를 다시 검토하고 `@ts-expect-error` 주석 제거 검토

### 참고
- 이 문제는 런타임에 영향을 주지 않으며, TypeScript 컴파일 시에만 발생합니다.
- CI에서는 `continue-on-error: true`로 설정되어 있어 빌드를 막지 않습니다.

---

## Expo 설정 정리 필요

### 현재 상태
`packages/app-expo` 패키지가 라이브러리 패키지에서 실제 Expo 앱으로 전환되면서:
- `App.tsx` 진입점 추가
- `app.json` 설정 파일 추가
- `package.json`의 `main` 필드 변경

### 향후 계획
- Expo 공식 구조(`expo/AppEntry.js`)에 맞게 정리
- `package.json.main`을 `expo/AppEntry.js`로 복원 검토
- TypeScript 설정 최적화

---

## Mock 모드 구현

### 현재 상태
`packages/app-expo/src/hud/accounting-api.ts`에 `mode: 'live' | 'mock'` 옵션이 추가되었습니다.

### 향후 개선
- `ManualReviewButton` 컴포넌트에서 직접 `fetch`를 사용하는 부분도 mock 모드 지원 필요
- Mock 응답 데이터를 별도 파일로 분리하여 관리

---

## 데이터베이스 스키마 문서화

### 현재 상태
데모 데이터 시드 스크립트(`scripts/seed_demo_data.mjs`)에서 사용하는 테이블 구조가 코드에만 존재합니다.

### 향후 개선
- 데이터베이스 스키마 문서 작성
- 각 테이블의 컬럼과 제약조건 명시
- JSONB 필드 구조 문서화

---

## 운영 스크립트 개선

### 현재 상태
- `scripts/ops_local_*.sh` - 로컬 환경 관리 스크립트
- `scripts/seed_demo_data.mjs` - 데모 데이터 시드

### 향후 개선
- 스크립트 오류 처리 강화
- 로깅 개선
- 스크립트 실행 전 사전 조건 체크 (Docker 실행 여부 등)

---

## Export 권한 완화 (파일럿 기간 한정)

### 현재 상태
`packages/bff-accounting/src/routes/exports.ts`에서 Export 엔드포인트(`POST /v1/accounting/exports/reports`)의 권한이 `operator`로 설정되어 있습니다.

### 배경
- 원래 설계: `requireRole('auditor')` - 감사자만 Export 가능
- 파일럿(R7-H) 기간: 운영 편의를 위해 `operator` 역할까지 허용

### 영향
- 파일럿 기간 동안 운영팀이 Export 기능을 더 쉽게 사용 가능
- 보안 정책은 유지되되, 역할 제한만 완화

### 향후 계획
- **R8에서 권한을 `auditor` 전용으로 되돌릴 것**
- 파일럿 종료 후 보안 정책 강화 검토

### 참고
- 이 변경사항은 의도된 완화이며, 파일럿 기간 동안만 유지됩니다.
- 운영/파일럿용으로만 사용하고, 프로덕션 배포 전 반드시 권한을 복원해야 합니다.

