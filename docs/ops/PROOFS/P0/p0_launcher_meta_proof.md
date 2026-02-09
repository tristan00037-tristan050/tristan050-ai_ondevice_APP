# P0 Launcher Meta Panel Proof (Text Evidence)

## 기준 시각
2026-02-09T04:25:28.449Z (UTC)

## 실행 경로 요약
Launcher (http://127.0.0.1:5179) → Gateway (http://127.0.0.1:8081)

## 실행 결과 (Meta Panel 8개 필드)

### Meta-Only 출력
```
request_id: req_1770614924891_r5u2jr9ct
compute_path: ondevice
pack_id/version/manifest_sha256: N/A / N/A / a226a255d769a4499e10edcac6a65fa343d5afaede714152e121aa05ffa1b8a6
latency_ms: 6
peak_mem_mb: N/A
result_fingerprint_sha256: 64d9eda5
reason_code_v1: OK
egress_attempt_blocked: false
```

## Quick Eval 결과

### 일관성 검증
```
일치: 10
불일치: 0
JSONL 저장키: p0_eval_jsonl
```

## PASS 조건
- ok=true
- 3블록 결과 존재 (block_1_policy, block_2_plan, block_3_checks)
- Meta Panel 8개 필드 값 존재:
  - request_id: 채워짐
  - compute_path: ondevice
  - manifest_sha256: 채워짐
  - latency_ms: 숫자 (6)
  - result_fingerprint_sha256: 8자리 해시 (64d9eda5)
  - reason_code_v1: OK
  - egress_attempt_blocked: false
- Quick Eval 통과: 일치 10 / 불일치 0

## 검증 결과
✅ PASS

## 주의사항
- 원문/프롬프트/출력 텍스트 저장 금지 (meta-only만 포함)
- request_id, manifest_sha256, result_fingerprint_sha256는 meta-only이므로 포함 허용

