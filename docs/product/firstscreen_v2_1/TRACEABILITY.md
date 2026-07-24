# v2.1 발견사항 추적성

상태는 로컬 구현 증거 기준이다. `LOCAL_PASS`는 원격 CI나 제품 release 승인을 의미하지 않는다.

| Finding | 분류 | 상태 | 제품 정본 / 검증 |
|---|---|---|---|
| BV14-P0-001 | C_GATE | BLOCKED_EXTERNAL | 원격 PR·canonical remote·signed provenance 실행 필요 |
| BV14-P0-002 | KEEP | LOCAL_PASS | `home/store.py`; missing-key continuity tests |
| BV14-P0-003 | KEEP | LOCAL_PASS | DB-authoritative workspace; mirror conflict tests |
| BV14-P0-004 | DESCOPE | BLOCKED_EXTERNAL | signed storage risk decision 없음 |
| BV14-P0-005 | KEEP | LOCAL_PASS | one transactional command ledger; replay/conflict tests |
| BV14-P0-006 | KEEP | LOCAL_PASS | capability actor; spoofed `X-Actor-ID` attack test |
| BV14-P0-007 | KEEP | LOCAL_PASS | field Unicode/bidi/score tests |
| BV14-P0-008 | C_GATE | BLOCKED_EXTERNAL | hosted clean frontend/JUnit/trace 실행 필요 |
| BV14-P0-009 | C_GATE | BLOCKED_EXTERNAL | signed macOS Keychain/app-data/VoiceOver E2E 필요 |
| BV14-P1-010 | DESCOPE | BLOCKED_EXTERNAL | signed risk decision 없음 |
| BV14-P1-011 | KEEP | LOCAL_PASS | terminal ledger, partial unique index, duplicate terminal test |
| BV14-P1-012 | KEEP | LOCAL_PASS | turn/model-request lifecycle correlation tests |
| BV14-P1-013 | DESCOPE | BLOCKED_EXTERNAL | audit chain signed risk decision 없음 |
| BV14-P1-014 | DESCOPE | BLOCKED_EXTERNAL | non-mac credential signed risk decision 없음 |
| BV14-P1-015 | DESCOPE | BLOCKED_EXTERNAL | recovery/rekey signed risk decision 없음 |
| BV14-P1-016 | PRODUCT_SEMANTICS | LOCAL_PASS | 전체 목록, profile badge/filter UI 및 API |
| BV14-P1-017 | KEEP_SUBORDINATE | LOCAL_PASS | immutable creation snapshot, audited reassignment |
| BV14-P1-018 | KEEP_SUBORDINATE | LOCAL_PASS | server UTC timestamp, monotonic sequence |
| BV14-P1-019 | KEEP_SUBORDINATE | LOCAL_PASS | finite non-bool score 0..1, negative-zero rejection |
| BV14-P1-020 | KEEP_SUBORDINATE | LOCAL_PASS | 30일 ledger horizon, bounded safe purge |
| BV14-P1-021 | KEEP_SUBORDINATE | LOCAL_PASS | immutable migration backup, manifest, known-good retention |
| BV14-P1-022 | KEEP_SUBORDINATE | LOCAL_PASS | schema-valid policy/measurement truth separation |
| BV14-P1-023 | KEEP_SUBORDINATE | LOCAL_PASS | FastAPI lifespan, flush/close/token clear |
| BV14-P1-024 | C_GATE | BLOCKED_EXTERNAL | Playwright/axe/keyboard/VoiceOver raw evidence 필요 |
| BV14-P1-025 | C_GATE | BLOCKED_EXTERNAL | main hosted run의 SBOM/attestation 필요 |
| BV14-P1-026 | KEEP_SUBORDINATE | LOCAL_PASS | exact Git regular-file archive/self-manifest verifier |
| BV14-P2-027 | DESCOPE | BLOCKED_EXTERNAL | signed performance risk decision 없음 |
| BV14-P2-028 | KEEP_SUBORDINATE | LOCAL_PASS | `OPERATIONS_RECOVERY_RUNBOOK.md` |

## 완료 판정

로컬 제품 경로의 구현 및 집중 검증은 완료했다. 그러나 repo-wide Python collection, hosted CI, signed macOS 실기기, VoiceOver, attestation, 대표 risk signature가 닫히지 않았으므로 `CODE_PASS=NO`, `MERGE_READY=NO`, `PRODUCT_RELEASE_READY=NO`, `RUNTIME_ACTIVATION_ALLOWED=0`이다.
