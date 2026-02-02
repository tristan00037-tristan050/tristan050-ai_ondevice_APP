# Proof Freshness Policy v1 (SSOT)

MAX_AGE_DAYS=14

Target:
- docs/ops/PROOFS/ONPREM_REAL_WORLD_PROOF_LATEST.md

Rule:
- LATEST 문서 내에 ISO 날짜(YYYY-MM-DD)가 최소 1개 존재해야 한다.
- 그 날짜의 최신값이 오늘 기준 MAX_AGE_DAYS 이내여야 한다.
- 민감정보/원문/비밀 생성은 하지 않는다(검사만).

