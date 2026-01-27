# ONPREM Install & Verify (Compose/Helm)

목표: 설치 후 "출력"으로만 정상 여부를 확인합니다.

## 1) Compose
- docs/ONPREM_COMPOSE_QUICKSTART.md 기준으로 실행
- /healthz, /readyz 확인

## 2) Helm
- secrets.enabled=true: chart가 Secret 생성
- secrets.enabled=false: 운영자가 existingSecretName Secret을 미리 생성해야 함
  - keys: DATABASE_URL, EXPORT_SIGN_SECRET

## 3) Output-only verify
- webcore_appcore_starter_4_17/scripts/ops/verify_onprem_install.sh 실행
