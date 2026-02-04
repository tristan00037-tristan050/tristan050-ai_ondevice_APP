# On-Prem Compose Quickstart (Phase 1 Standard)

목적: 고객사(기업 내부망)에서 Docker Compose로 BFF+DB를 빠르게 기동하고, healthz/readyz 및 build anchor를 출력 기반으로 검증한다.

## 0) 전제
- Docker Engine + Docker Compose v2
- 내부망에서만 접근(외부 공개 금지)

## 1) 기동(Quickstart)
```bash
cd "$(git rev-parse --show-toplevel)/webcore_appcore_starter_4_17"
docker compose up -d --build
```

## 2) 상태 확인(필수)

Health:

```bash
curl -fsS http://127.0.0.1:8081/healthz | head
```

Ready(DB 연결/마이그레이션 상태):

```bash
curl -fsS http://127.0.0.1:8081/readyz | head
```

## 3) build anchor 검증(필수, 출력 기반 판정)

정본 스크립트로만 판정한다.

```bash
BASE_URL=http://127.0.0.1:8081 bash scripts/ops/verify_build_anchor.sh
```

## 4) 종료
```bash
docker compose down -v
```

## 5) 운영 주의

- DB 비밀번호/EXPORT_SIGN_SECRET 등은 프로덕션에서 반드시 교체
- 포트(8081/5432)는 내부망만 허용

