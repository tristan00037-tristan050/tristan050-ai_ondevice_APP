# BFF Secret Schema v1 (PR-P0-DEPLOY-02)

Meta-only contract: BFF 배포에 필요한 Secret의 필수 키·형식 규칙. 값 원문 출력 금지.

## Required keys

| Key | Description |
|-----|-------------|
| `DATABASE_URL` | PostgreSQL connection URL (scheme, host, port required; empty forbidden) |
| `EXPORT_SIGN_SECRET` | Signing secret for export; empty forbidden; minimum length 16 (value never logged) |

## Rules

1. **No value output**: 스크립트/콘솔에 시크릿·접속문자열 원문 출력 0. key=value 중 value는 절대 출력하지 않음.
2. **DATABASE_URL**:
   - URL parse 가능 (scheme 존재, host/port 존재).
   - 빈 문자열 금지.
3. **EXPORT_SIGN_SECRET**:
   - 빈 문자열 금지.
   - 길이 >= 16 (값 출력 금지, 길이만 검사).
4. **Fail-closed**: 누락/빈값/URL parse 불가 시 PR 단계에서 즉시 BLOCK.

## Verification

- `scripts/verify/verify_bff_secret_schema_v1.sh`: 입력은 환경변수만; 값 출력 0; meta-only 출력(key=value, fail_class/fail_hint).
