# IP3 v1.3 Threat Model and Failure Taxonomy

## 보호자산 8종

1. device telemetry integrity
2. policy decision integrity
3. routing decision integrity
4. model executable status integrity
5. audit chain integrity
6. user context privacy
7. latency and fail-safe evidence integrity
8. package seal integrity

## 위협 12종

1. telemetry spoofing
2. battery/thermal source tampering
3. policy bypass
4. local model executable overclaim
5. external API leakage
6. raw content persistence
7. audit chain truncation
8. sample-to-real evidence escalation
9. CI-to-physical evidence escalation
10. replay harness poisoning
11. latency benchmark cherry-picking
12. dirty package insertion

## 실패 9종

1. missing platform telemetry
2. malformed telemetry schema
3. PEP deny
4. IP1 forward false
5. thermal critical
6. network unavailable
7. restricted data cannot route locally
8. bridge unavailable
9. package seal mismatch

## Fail-closed 원칙

위협 또는 실패가 감지되면 `blocked`, `fallback`, `failed_closed` 중 하나로 종료하고 production claim을 금지합니다.
