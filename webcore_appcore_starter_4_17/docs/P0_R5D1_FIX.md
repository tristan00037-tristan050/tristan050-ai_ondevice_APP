# P0 결함 수정: r5d-1 서버 측 필터링

검토팀이 지적한 P0(치명적) 아키텍처 결함을 수정했습니다.

## 🚨 P0 결함 (r5d-1)

**문제**: `GET /reports` 엔드포인트가 Query Parameter를 지원하지 않아 클라이언트 측 필터링을 유발하는 아키텍처 결함

**영향**: 
- 모든 리포트를 클라이언트로 전송 후 클라이언트에서 필터링
- 네트워크 대역폭 낭비
- 확장성 문제 (리포트 수가 많아질수록 성능 저하)

---

## ✅ 수정 내용

### 1. Collector 서버 측 필터링 구현

**파일**: `packages/collector-node-ts/src/routes/reports.ts`

**추가된 Query Parameters**:
- `severity`: `info`, `warn`, `block` 중 하나
- `policy_version`: 정책 버전 (부분 일치)
- `since`: 타임스탬프 (이후 리포트만 반환)
- `page`: 페이지 번호 (기본값: 1)
- `limit`: 페이지당 항목 수 (기본값: 20, 최대: 100)

**응답 형식 변경**:
```json
{
  "reports": [
    {
      "id": "report-123",
      "createdAt": 1234567890,
      "updatedAt": 1234567890,
      "severity": "block",
      "policyVersion": "v1"
    }
  ],
  "pagination": {
    "page": 1,
    "limit": 20,
    "totalCount": 100,
    "totalPages": 5
  }
}
```

**구현 사항**:
1. Query Parameter 파싱 및 유효성 검증
2. 서버 측 필터링 (severity, policy_version, since)
3. 서버 측 페이지네이션 (page, limit)
4. ETag 생성 (필터링 및 페이지네이션 결과 기반)

---

### 2. Ops Console 클라이언트 측 필터링 제거

**파일**: `packages/ops-console/src/pages/Reports.tsx`

**변경 사항**:
- ❌ 제거: `useMemo`를 사용한 클라이언트 측 필터링
- ✅ 추가: API 재호출을 통한 서버 측 필터링
- ✅ 추가: 필터 변경 시 자동 API 재호출
- ✅ 추가: 페이지네이션 정보 표시

**변경 전**:
```typescript
// 클라이언트 측 필터링 (문제)
const filteredReports = useMemo(() => {
  let filtered = [...reports];
  if (filters.severity !== 'all') {
    filtered = filtered.filter(r => r.severity === filters.severity);
  }
  // ...
  return filtered;
}, [reports, filters]);
```

**변경 후**:
```typescript
// 서버 측 필터링 (수정)
const loadReports = useCallback(async (pageNum: number = currentPage) => {
  const apiParams = buildApiParams(pageNum);
  const response = await getReports(apiParams);
  setReports(response.reports);
  setTotalCount(response.pagination.totalCount);
  setTotalPages(response.pagination.totalPages);
}, [buildApiParams, currentPage]);
```

---

### 3. API 래퍼 업데이트

**파일**: `packages/ops-console/src/api/reports.ts`

**변경 사항**:
- `getReports()` 함수에 Query Parameter 지원 추가
- `ReportsResponse` 인터페이스 추가 (pagination 정보 포함)
- `GetReportsParams` 인터페이스 추가

---

## 🧪 검증 시나리오

### 서버 측 필터링 테스트

```bash
# severity 필터
curl -H "X-Tenant: default" \
     -H "X-Api-Key: collector-key" \
     "http://localhost:9090/reports?severity=block"

# policy_version 필터
curl -H "X-Tenant: default" \
     -H "X-Api-Key: collector-key" \
     "http://localhost:9090/reports?policy_version=v1"

# since 필터 (최근 24시간)
curl -H "X-Tenant: default" \
     -H "X-Api-Key: collector-key" \
     "http://localhost:9090/reports?since=$(($(date +%s) - 86400))000"

# 페이지네이션
curl -H "X-Tenant: default" \
     -H "X-Api-Key: collector-key" \
     "http://localhost:9090/reports?page=2&limit=10"

# 복합 필터
curl -H "X-Tenant: default" \
     -H "X-Api-Key: collector-key" \
     "http://localhost:9090/reports?severity=block&policy_version=v1&page=1&limit=20"
```

### 유효성 검증 테스트

```bash
# 잘못된 severity 값
curl -H "X-Tenant: default" \
     -H "X-Api-Key: collector-key" \
     "http://localhost:9090/reports?severity=invalid"
# 400 Bad Request 예상

# 잘못된 page 값
curl -H "X-Tenant: default" \
     -H "X-Api-Key: collector-key" \
     "http://localhost:9090/reports?page=0"
# 400 Bad Request 예상

# 잘못된 limit 값
curl -H "X-Tenant: default" \
     -H "X-Api-Key: collector-key" \
     "http://localhost:9090/reports?limit=200"
# 400 Bad Request 예상
```

---

## ✅ 수정 완료 확인

### 서버사이드 (Collector)
- ✅ `GET /reports`에 Query Parameter 지원 추가
- ✅ 서버 측 필터링 구현 (severity, policy_version, since)
- ✅ 서버 측 페이지네이션 구현 (page, limit)
- ✅ 유효성 검증 추가
- ✅ ETag 생성 (필터링 결과 기반)
- ✅ TypeScript 빌드 성공

### 클라이언트사이드 (Ops Console)
- ✅ `useMemo` 클라이언트 측 필터링 제거
- ✅ API 재호출을 통한 서버 측 필터링 구현
- ✅ 필터 변경 시 자동 API 재호출
- ✅ 페이지네이션 정보 표시
- ✅ TypeScript 오류 없음

---

## 📋 API 명세

### GET /reports

**Query Parameters**:
- `severity` (optional): `info` | `warn` | `block`
- `policy_version` (optional): string (부분 일치)
- `since` (optional): number (타임스탬프, 밀리초)
- `page` (optional): number (기본값: 1, 최소: 1)
- `limit` (optional): number (기본값: 20, 범위: 1-100)

**Response**:
```json
{
  "reports": ReportSummary[],
  "pagination": {
    "page": number,
    "limit": number,
    "totalCount": number,
    "totalPages": number
  }
}
```

**Headers**:
- `ETag`: 필터링 및 페이지네이션 결과 기반 ETag
- `Cache-Control`: `private, must-revalidate`

---

## 🔒 불변 원칙 준수

1. **테넌트 격리**: 모든 필터링은 테넌트별로 적용
2. **ETag 안정성**: 필터링 및 페이지네이션 결과 기반 ETag 생성
3. **정렬 고정**: createdAt 내림차순, id 오름차순 유지

---

## ✅ P0 결함 해결 확인

**r5d-1: 서버 측 필터링** - ✅ 완료

- ✅ Collector: Query Parameter 지원 추가
- ✅ Ops Console: 클라이언트 측 필터링 제거
- ✅ API 재호출로 변경
- ✅ 모든 검증 통과

**이제 검토팀의 승인을 받을 수 있습니다.**


