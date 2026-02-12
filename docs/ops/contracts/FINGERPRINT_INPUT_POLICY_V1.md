# FINGERPRINT_INPUT_POLICY_V1

FINGERPRINT_INPUT_POLICY_V1_TOKEN=1

금지 키(지문 입력에 포함되면 즉시 BLOCK):
- request_id
- ts_utc
- nonce
- manifest
- run_id

규칙:
- 위 금지 키가 입력 객체에 존재하면 런타임에서 예외(code-only)로 중단한다.
- verify는 설치/다운로드/빌드/네트워크 없이 판정만 출력한다.
