# ONPREM_PROOF_LATEST_POLICY_V1

ONPREM_PROOF_LATEST_POLICY_V1_TOKEN=1

## 목적
- onprem real-world proof LATEST 문서는 PASS 마커만 포함해야 함
- 실패 텍스트/로그는 LATEST에 포함 금지 (archive로 분리)
- 민감 패턴 검사 (SSOT 기반)
- 긴 라인 차단 (가독성/보안)

## 규칙
- LATEST 파일: `docs/ops/PROOFS/ONPREM_REAL_WORLD_PROOF_LATEST.md`
- PASS 마커: `EXIT=0` 또는 `ok=true` 등 단일 마커 1줄만 허용
- 실패 패턴 금지: `EXIT=1`, `FAIL:`, `BLOCK:`, `error:`, `Error:`, `ERROR:` 등
- 민감 패턴 SSOT: `docs/ops/contracts/PROOF_SENSITIVE_PATTERNS_V1.txt`
- 긴 라인 차단: 500자 초과 라인 BLOCK
- 화이트리스트: 허용된 마커만 통과

## DoD 키
- `ONPREM_LATEST_PASS_MARKER_V1_OK=1`: PASS 마커 존재
- `ONPREM_LATEST_NO_FAILURE_TEXT_V1_OK=1`: 실패 텍스트 없음
- `ONPREM_LATEST_SENSITIVE_SCAN_V1_OK=1`: 민감 패턴 없음
- `ONPREM_LATEST_LONG_LINE_BLOCK_V1_OK=1`: 긴 라인 없음

