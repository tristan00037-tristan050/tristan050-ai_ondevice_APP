# SVR-03 Reason Codes v1

## 원칙
- 서버/SDK/로그/텔레메트리/UI가 같은 reason_code 문자열을 사용한다.
- meta-only: reason_code와 최소 맥락만 남긴다(원문/식별자/긴 텍스트 금지).

## 공통(v1)
- SIGNATURE_MISSING
- SIGNATURE_INVALID
- CANONICAL_PAYLOAD_INVALID
- KEY_ID_UNKNOWN
- RBAC_PERMISSION_DENIED

## Apply/Rollback(v1)
- APPLY_DENY_BY_DEFAULT
- APPLY_TARGET_INVALID
- ROLLBACK_NOT_ALLOWED

