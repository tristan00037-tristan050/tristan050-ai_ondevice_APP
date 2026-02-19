# Ondevice Model Execution v0 Proof (Track B-1)

**Date**: 2026-02-02  
**Status**: PASS (meta-only only)

이 문서는 온디바이스 실모델 실행 v0 검증의 출력 기반 증빙입니다.

## 검증 항목

### 1. Good Pack 실행 (실제 연산 1회 이상)

- **compute_path**: `ondevice`
- **pack_id**: `accounting_v0`
- **pack_version**: `0.1.0`
- **manifest_sha256**: (64자 hex 해시)
- **latency_ms**: (숫자, ms 단위)
- **backend**: `ondevice`
- **applied**: `true`
- **reason_code**: `APPLY_OK`

**Note**: 현재는 형태 생성 단계이며, 실제 모델 실행(모델 파일 + 실행 엔진 + 입력 → 결과)은 후속 PR에서 추가됩니다.

### 2. Bad Pack 차단 (검증 우회 금지)

- **서명 불일치**: `applied=false`, `reason_code=SIGNATURE_INVALID`, 상태 불변 확인
- **만료/필수 필드 누락**: `applied=false`, 상태 불변 확인

### 3. 원문 저장 0 검증

- 금지 키/패턴 스캔: `raw_text`, `prompt`, `messages`, `document_body`, `BEGIN .* PRIVATE KEY`, env형 `_TOKEN`/`_PASSWORD` 등
- 검증 결과: 금지 패턴 미검출 (meta-only만 출력)

### 4. 외부망 차단 증빙

- **egress_attempt_blocked**: `true`
- **compute_path**: `ondevice`
- **note**: 실행 경로에서 외부 네트워크 호출 없음 (정적 검증)

## Meta-Only 마커 예시

```json
{
  "request_id": "req_ondevice_<timestamp>",
  "compute_path": "ondevice",
  "pack_id": "accounting_v0",
  "pack_version": "0.1.0",
  "manifest_sha256": "<64자 hex>",
  "latency_ms": <숫자>,
  "backend": "ondevice",
  "applied": true,
  "reason_code": "APPLY_OK"
}
```

## 제약사항

- 원문/원문 조각이 로그/이벤트/리포트/증빙에 포함되지 않음
- 모든 출력은 meta-only (해시/길이/카운트만 허용)
- 실제 모델 실행은 후속 PR에서 추가 예정

## 검증 스크립트

- `scripts/verify/verify_ondevice_model_exec_v0.sh`
- DoD Keys:
  - `ONDEVICE_MODEL_EXEC_V0_OK=1`
  - `MODEL_PACK_VERIFY_REQUIRED_OK=1`
  - `ONDEVICE_EGRESS_DENY_PROOF_OK=1`
  - `ONDEVICE_NO_RAW_STORAGE_OK=1`

