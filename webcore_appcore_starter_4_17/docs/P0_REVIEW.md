# P0 재검토 결과 (서버사이드 기준)

## ✅ P0-1: 업로더 큐 보안 강화

**상태**: ✅ 통과

**확인 사항**:
- API Key가 큐에 저장되지 않음
- 큐 원소는 `report`, `md`, `tenantId`, `attempt`, `createdAt`만 포함
- API Key는 메모리/옵션으로만 사용

**파일**: `packages/app-expo/src/lib/uploader.ts` (클라이언트 사이드)

---

## ⚠️ P0-2: Collector 테넌트/권한 가드 강제

**상태**: ⚠️ 부분 통과 (토큰 검증 로직 수정 필요)

### ✅ 통과 항목

1. **모든 엔드포인트에 requireTenantAuth 적용**:
   - ✅ `GET /reports` - requireTenantAuth
   - ✅ `GET /reports/:id` - requireTenantAuth
   - ✅ `POST /reports/:id/sign` - requireTenantAuth
   - ✅ `GET /reports/:id/sign-history` - requireTenantAuth
   - ✅ `GET /reports/:id/bundle-meta` - requireTenantAuth
   - ✅ `GET /timeline` - requireTenantAuth
   - ✅ `POST /ingest/qc` - requireTenantAuth
   - ✅ `POST /admin/retention/run` - requireTenantAuth

2. **서명 토큰에 tenant 포함**:
   - ✅ 토큰 페이로드에 `tenantId` 포함
   - ✅ 멱등성 보장 (캐시 사용)

3. **ETag 안정성**:
   - ✅ 목록 정렬 고정 (ID/시각 기준)

### ⚠️ 수정 필요 항목

**문제**: `verifySignToken`에서 토큰 페이로드를 디코딩하지 않고 단순히 HMAC 재계산만 수행

**현재 구현**:
```typescript
// 토큰 검증: 요청 파라미터로 토큰 재계산
const expectedToken = crypto
  .createHmac('sha256', signSecret)
  .update(JSON.stringify({ reportId, tenantId }))
  .digest('hex');

if (token !== expectedToken) {
  res.status(403).json({ error: 'Invalid token' });
  return;
}
```

**문제점**:
- 토큰 생성 시 `{ reportId, tenantId, expiresAt }`를 포함하지만
- 검증 시에는 요청 파라미터(`req.params.id`, `req.headers['x-tenant']`)로만 재계산
- 토큰에서 실제 페이로드를 추출하지 못함
- 토큰의 `expiresAt` 검증 불가
- 토큰 페이로드의 `tenantId`와 `reportId`를 요청 파라미터와 교차검증하지 못함

**수정 방안**:
1. 토큰 생성 시 페이로드를 base64로 인코딩하여 토큰에 포함
2. `verifySignToken`에서 토큰을 디코딩하여 페이로드 추출
3. 페이로드의 `tenantId`, `reportId`, `expiresAt` 검증
4. 요청 파라미터와 페이로드 교차검증

---

## 📋 수정 계획

### 1. 토큰 구조 변경
- 형식: `base64(payload).signature`
- payload: `{ reportId, tenantId, expiresAt }` (JSON)
- signature: HMAC-SHA256(payload, secret)

### 2. verifySignToken 수정
- 토큰에서 페이로드 추출
- 페이로드 디코딩
- `expiresAt` 검증
- 페이로드의 `tenantId`와 `reportId`를 요청 파라미터와 교차검증
- 서명 검증

---

## 🧪 검증 시나리오

### 테넌트 격리 테스트
```bash
# 올바른 테넌트/키
curl -H "X-Tenant: default" \
     -H "X-Api-Key: collector-key" \
     http://localhost:9090/reports

# 잘못된 키
curl -H "X-Tenant: default" \
     -H "X-Api-Key: wrong-key" \
     http://localhost:9090/reports
# 403 Forbidden 예상
```

### 토큰 교차검증 테스트
```bash
# 리포트 서명
TOKEN=$(curl -X POST \
  -H "X-Tenant: default" \
  -H "X-Api-Key: collector-key" \
  http://localhost:9090/reports/report-123/sign | jq -r .token)

# 올바른 tenant/reportId로 다운로드
curl -H "X-Tenant: default" \
  "http://localhost:9090/reports/report-123/bundle.zip?token=$TOKEN"
# 200 OK 예상

# 잘못된 tenant로 다운로드 시도
curl -H "X-Tenant: teamA" \
  "http://localhost:9090/reports/report-123/bundle.zip?token=$TOKEN"
# 403 Forbidden 예상 (토큰 페이로드의 tenantId와 불일치)
```

---

## ✅ 다음 단계

1. ✅ P0-1 확인 완료
2. ⚠️ P0-2 토큰 검증 로직 수정 필요
3. 🔄 수정 후 재검토
4. ✅ 통과 시 r5d-2 → r5d-3 → r5d-4 → r5d-5 순서로 진행


