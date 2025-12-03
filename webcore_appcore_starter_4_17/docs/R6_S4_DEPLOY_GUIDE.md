# R6-S4 배포 가이드

## 1) 태그 생성 → 릴리스 파이프라인 기동

```bash
git tag r6-s4-$(date +%Y%m%d)
git push origin --tags
```

## 2) GH Secrets (필수)

- `KUBE_CONFIG`: kubeconfig 전체 내용
- `DATABASE_URL`: Postgres 접속 문자열
- `EXPORT_SIGN_SECRET`: HMAC 서명 키

## 3) Helm 수동 배포(선택)

```bash
helm upgrade --install bff charts/bff-accounting \
  --set image.repository=ghcr.io/OWNER/REPO/bff-accounting \
  --set image.tag=TAG \
  --set env.EXPORT_SIGN_SECRET=*** \
  --set env.DATABASE_URL=postgres://...
```

## 4) 관측 확인

- `/ready` 200 OK
- `/metrics` 지표 노출 (http_request_duration_seconds)
- 구조화 로그(JSON)에 `id/tenant/idem/ms` 포함

## 5) 레이트 리밋 확인

- 일반: 1분 300요청
- Approvals: 1분 120요청
- Exports: 1분 60요청
- Reconciliation: 1분 120요청

## 6) 보안 헤더 확인

- Helmet 보안 헤더 적용
- CORS 설정
- PII 마스킹 (로그)

