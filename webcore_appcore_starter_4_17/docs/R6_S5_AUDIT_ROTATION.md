# R6-S5: Audit Trail & Secret Rotation

## 1) 시크릿 로테이션 (무중단)

1. 새 키 발급 → `EXPORT_SIGN_SECRET_PREV` 에 기존 키, `EXPORT_SIGN_SECRET` 에 새 키 설정
2. 24~48시간 운영 후(기존 URL 만료 대기) `EXPORT_SIGN_SECRET_PREV` 제거
3. Helm:

```bash
helm upgrade --install bff charts/bff-accounting \
  --set env.EXPORT_SIGN_SECRET="new-key" \
  --set env.EXPORT_SIGN_SECRET_PREV="old-key"
```

## 2) 보관/정리

- `RETENTION_DAYS` 기본 30일
- CronJob: 매일 03:00 실행, 만료 Export/Recon 정리
- 규정 변경 시 `values.yaml` 수정 후 배포

## 3) 감사 로그 조회

### 인덱스 활용
- `idx_audit_tenant_ts`: 테넌트별 시간순 조회
- `idx_audit_action_ts`: 액션별 시간순 조회

### 예시 쿼리
```sql
-- 최근 90일 감사 이벤트
SELECT * FROM accounting_audit_events
WHERE tenant = 'default' AND ts > NOW() - INTERVAL '90 days'
ORDER BY ts DESC;

-- 특정 액션 조회
SELECT * FROM accounting_audit_events
WHERE action = 'approval_apply' AND ts > NOW() - INTERVAL '30 days'
ORDER BY ts DESC;
```

## 4) 운영 팁

### 키 로테이션
- `EXPORT_SIGN_SECRET_PREV`는 최대 만료기간(예: 7일) 이후 제거
- 무중단 로테이션을 위해 이중 검증 지원

### 감사 조회
- 테넌트/액션 기준 인덱스 존재 → 최근 90일 쿼리 매우 빠름
- JSONB `payload` 필드로 상세 정보 저장

### 보관 기준
- `cleanup.retentionDays`를 Helm Values로 환경별(DEV/STG/PROD) 구분
- 감사 이벤트는 별도 보관 정책 적용 (cleanup 대상 아님)

