# Ondevice Real Compute Once Proof (Track B-1.1)

**Date**: 2026-02-05  
**Status**: PASS (meta-only only)

이 문서는 온디바이스 실연산 1회 검증의 출력 기반 증빙입니다.

## 검증 항목

### 1. 실연산 1회 수행

- **연산**: 입력(meta-only)을 해시 계산으로 변환 (SHA256)
- **목적**: "문장 생성"이 아니라 연산 1회 수행 + 지문 변화
- **결과**: `result_fingerprint_sha256` (64자 hex 해시)

### 2. Good Pack 실행

- **compute_path**: `ondevice`
- **pack_id**: `accounting_v0`
- **pack_version**: `0.1.0`
- **manifest_sha256**: (64자 hex 해시)
- **latency_ms**: (숫자, ms 단위)
- **backend**: `ondevice`
- **applied**: `true`
- **reason_code**: `APPLY_OK`
- **result_fingerprint_sha256**: (64자 hex 해시, 실연산 결과 지문)

### 3. Bad Pack 차단 (검증 우회 금지)

- **서명 불일치**: `applied=false`, `reason_code=SIGNATURE_INVALID`, 상태 불변 확인

### 4. 원문 저장 0 검증

- 금지 키/패턴 스캔: `raw_text`, `prompt`, `messages`, `document_body`, `BEGIN .* PRIVATE KEY`, env형 `_TOKEN`/`_PASSWORD` 등
- 검증 결과: 금지 패턴 미검출 (meta-only만 출력)

## Meta-Only 마커 예시

```json
{
  "request_id": "req_real_compute_<timestamp>",
  "compute_path": "ondevice",
  "pack_id": "accounting_v0",
  "pack_version": "0.1.0",
  "manifest_sha256": "<64자 hex>",
  "latency_ms": <숫자>,
  "backend": "ondevice",
  "applied": true,
  "reason_code": "APPLY_OK",
  "result_fingerprint_sha256": "<64자 hex>"
}
```

## 제약사항

- 원문/원문 조각이 로그/이벤트/리포트/증빙에 포함되지 않음
- 모든 출력은 meta-only (해시/길이/카운트만 허용)
- 실연산 결과는 `result_fingerprint_sha256`로만 표현 (원문 저장 금지)

## 검증 스크립트

- `scripts/verify/verify_ondevice_real_compute_once.sh`
- DoD Keys:
  - `ONDEVICE_REAL_COMPUTE_ONCE_OK=1`
  - `ONDEVICE_RESULT_FINGERPRINT_OK=1`
  - `ONDEVICE_COMPUTE_PATH_ONDEVICE_OK=1`

