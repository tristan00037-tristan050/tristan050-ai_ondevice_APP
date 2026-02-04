# R5d 서버사이드 기준 재검토 결과

서버사이드 기준으로 r5d-2 → r5d-3 → r5d-4 → r5d-5 작업을 재검토하고 보완한 결과입니다.

## ✅ r5d-2: 서명 감사 로그 (서버사이드)

**상태**: ✅ 완료

**구현 사항**:
- 서명 이력 저장소 (`signHistory` 배열)
- `POST /reports/:id/sign`에서 서명 이력 자동 저장
- `GET /reports/:id/sign-history` API 엔드포인트
- 테넌트 격리 보장
- 이력 최대 1000개 유지 (오래된 것 자동 제거)

**파일**: `packages/collector-node-ts/src/routes/reports.ts`

**API 응답 예시**:
```json
{
  "reportId": "report-123",
  "history": [
    {
      "requestedBy": "default",
      "issuedAt": 1234567890,
      "expiresAt": 1234571490,
      "createdAt": 1234567890,
      "tokenPreview": "eyJhbGciOiJIUzI1..."
    }
  ],
  "count": 1
}
```

---

## ✅ r5d-3: 번들 메타 정보 (서버사이드)

**상태**: ✅ 완료

**구현 사항**:
- `GET /reports/:id/bundle-meta` API 엔드포인트
- 번들 구성 파일 목록 (qc_report.json, qc_report.md)
- 파일 크기 계산
- SHA256 체크섬 계산
- ZIP 크기 추정 (10% 오버헤드)
- 테넌트 격리 보장

**파일**: `packages/collector-node-ts/src/routes/reports.ts`

**API 응답 예시**:
```json
{
  "reportId": "report-123",
  "files": [
    {
      "name": "qc_report.json",
      "size": 1024,
      "checksum": "abc123..."
    }
  ],
  "totalFiles": 1,
  "totalSize": 1024,
  "estimatedZipSize": 1126,
  "checksums": {
    "qc_report.json": "abc123..."
  },
  "createdAt": 1234567890,
  "updatedAt": 1234567890
}
```

---

## ✅ r5d-4: 타임라인 API BLOCK 집계 (서버사이드)

**상태**: ✅ 완료 (수정 완료)

**수정 사항**:
- 기존: 하드코딩된 0 값만 반환
- 수정: 실제 리포트 데이터에서 severity 집계

**구현 사항**:
- 테넌트별 리포트 필터링
- 시간 범위 필터링 (window_h 기준)
- 1시간 단위 버킷 생성
- 각 버킷별 severity 집계 (info, warn, block)
- 리포트의 최고 severity 추출 (block > warn > info)

**파일**: `packages/collector-node-ts/src/index.ts`

**집계 로직**:
1. 테넌트별 리포트 필터링
2. 시간 범위 내 리포트 필터링 (startTime ~ now)
3. 1시간 단위 버킷 생성
4. 각 버킷별 리포트의 최고 severity 집계
5. 버킷별 info/warn/block 카운트 반환

**API 응답 예시**:
```json
{
  "window_h": 24,
  "buckets": [
    {
      "time": 1234567890,
      "info": 5,
      "warn": 2,
      "block": 1
    },
    {
      "time": 1234571490,
      "info": 3,
      "warn": 1,
      "block": 0
    }
  ]
}
```

---

## ✅ r5d-5: 권한 레벨 (서버사이드)

**상태**: ✅ 불필요 (클라이언트 사이드만 구현)

**설명**:
- 권한 레벨은 클라이언트 사이드(ops-console)에서만 관리
- 서버사이드(Collector)는 모든 엔드포인트에 `requireTenantAuth` 적용
- 다운로드 권한은 클라이언트에서 UI 제어

---

## 📋 서버사이드 API 엔드포인트 요약

### Reports API
- `GET /reports` - 리포트 목록 (severity, policyVersion 포함)
- `GET /reports/:id` - 리포트 상세
- `POST /reports/:id/sign` - 리포트 서명 (멱등성 보장)
- `GET /reports/:id/sign-history` - 서명 이력 조회 (r5d-2)
- `GET /reports/:id/bundle-meta` - 번들 메타 정보 (r5d-3)
- `GET /reports/:id/bundle.zip` - 번들 다운로드 (토큰 검증)

### Timeline API
- `GET /timeline?window_h=24` - 타임라인 조회 (severity 집계, r5d-4)

### 기타 API
- `POST /ingest/qc` - 리포트 인제스트
- `POST /admin/retention/run` - 보존 정책 실행

---

## 🔒 테넌트 격리 보장

모든 엔드포인트에 `requireTenantAuth` 미들웨어 적용:
- X-Tenant 헤더 검증
- X-Api-Key 헤더 검증
- API_KEYS 환경변수 매핑 검증
- 테넌트별 데이터 격리

---

## ✅ 최종 상태

- **r5d-2**: ✅ 서명 감사 로그 API 완료
- **r5d-3**: ✅ 번들 메타 정보 API 완료
- **r5d-4**: ✅ 타임라인 API severity 집계 완료
- **r5d-5**: ✅ 권한 레벨 (클라이언트 사이드만, 서버사이드 불필요)

모든 서버사이드 작업이 완료되었습니다.


