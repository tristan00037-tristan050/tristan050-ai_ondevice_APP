# ALGO-CORE-06 Prod Key Management (SSOT)

목적
- prod 환경에서 ALGO-CORE 서명 키가 없거나 잘못되면 서비스가 "뜨지 않게" (fail-closed) 한다.
- 키 주입/회전/허용 정책을 문서(SSOT)로 고정하여 운영 실수를 재발 0으로 만든다.

Prod 모드 동작(레포 구현 규율)
- ALGO_CORE_MODE=prod 일 때, 아래 조건을 만족하지 못하면 bff-accounting은 부트 단계에서 즉시 종료해야 한다.
  - ALGO_CORE_SIGN_PUBLIC_KEY_B64 존재
  - ALGO_CORE_SIGN_PRIVATE_KEY_B64 존재
  - ALGO_CORE_SIGNING_KEY_ID 존재
  - ALGO_CORE_ALLOWED_SIGNING_KEY_IDS 존재(쉼표 CSV)
  - ALGO_CORE_SIGNING_KEY_ID가 ALGO_CORE_ALLOWED_SIGNING_KEY_IDS에 포함

필수 환경변수(Prod)
- ALGO_CORE_MODE=prod
- ALGO_CORE_SIGN_PUBLIC_KEY_B64=<base64(pem spki)>
- ALGO_CORE_SIGN_PRIVATE_KEY_B64=<base64(pem pkcs8)>
- ALGO_CORE_SIGNING_KEY_ID=<string>
- ALGO_CORE_ALLOWED_SIGNING_KEY_IDS=<csv; include key_id>

키 생성/주입 절차(요약)
1) 키 생성
- scripts/ops/algo_core_keygen.sh 실행
- 출력된 PUBLIC/PRIVATE(B64 PEM)와 KEY_ID를 보관

2) 운영 환경에 주입
- (GitHub Actions / 서버 환경변수 / 배포 시스템) 중 한 군데를 단일 진실원으로 선택
- 위 환경변수 5개를 정확히 설정

3) 회전(키 교체)
- 새 키를 생성하고, allowlist에 "기존+신규"를 함께 넣은 상태로 배포
- 정상 동작 확인 후 allowlist에서 기존 KEY_ID 제거
- 최종적으로 신규 KEY_ID만 남김

금지
- 레포에 PRIVATE KEY 원문/복호화 가능한 형태를 커밋 금지
- prod에서 allowlist 없이 KEY_ID만 설정하는 방식 금지(반드시 allowlist 강제)
