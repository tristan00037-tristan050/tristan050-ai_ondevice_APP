# 문제 해결 가이드

## TypeScript 컴파일 오류 해결 완료

### 문제
Express의 `Request` 타입에 `tenantId` 속성을 추가했지만 TypeScript가 인식하지 못함.

### 해결
1. `src/types/express.d.ts` 파일 생성 - Express 타입 확장
2. 모든 파일에서 타입 확장 로드: `import './types/express'`
3. `tsconfig.json`에 `typeRoots` 추가

### 변경 사항
- `src/types/express.d.ts` - Express Request 인터페이스 확장
- 모든 라우트 핸들러에서 타입 단언 제거
- `req.tenantId` 직접 사용 가능

## 빌드 성공 확인

```bash
cd packages/collector-node-ts
npm run build
# ✅ 성공: 오류 없음
```

## 서버 실행

```bash
export API_KEYS="default:collector-key"
export EXPORT_SIGN_SECRET=dev-secret
export RETAIN_DAYS=30
npm start
```

## 모듈 로드 오류 (ERR_MODULE_NOT_FOUND)

ESM 모듈에서는 import 경로에 `.js` 확장자가 필요할 수 있습니다.

해결: 동적 import 시 `.js` 확장자 사용
```typescript
const reportsModule = await import('./routes/reports.js');
```


