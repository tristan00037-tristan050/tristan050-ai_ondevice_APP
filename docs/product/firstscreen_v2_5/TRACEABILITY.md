# FirstScreen v2.5 요구사항 추적

| Finding | 구현 정본 | 현재 판정 |
|---|---|---|
| FS23-P0-001 | `firstscreen_trust.py`, bootstrap/root contracts | Python 제품 경로 구현·공격 차단; signed app bootstrap 미실증으로 OPEN |
| FS23-P0-002 | signed revocation/version/previous digest/trusted state checks | 알고리즘 구현; macOS Keychain CAS 미구현·미실증으로 OPEN |
| FS23-P0-003 | BUILD_CONTEXT, release-subject verifier, bundle/SBOM binding | unsigned developer handoff만 생성; signed native/release subject 부재로 OPEN |
| FS23-P0-004 | v2.5 repo-wide required CI | 로컬 저장소 84 fail·15 error로 OPEN |
| FS23-P0-005 | branch coverage gate and attack tests | aggregate 85.69%; decision 100%·mutation 미실행으로 OPEN |
| FS23-P0-006 | delegated expiring risk decision | verifier 구현; owner artifact 부재로 BLOCKED_OWNER |
| FS23-P0-007 | single branch workflow, source provenance, consumer verify | canonical remote/PR 미실행으로 BLOCKED_EXTERNAL |
| FS23-P0-008 | macOS/Windows/browser/M3 jobs | signed app·실기기 미실행 |
| FS23-P1-009 | in-process `cryptography` Ed25519 | `ssh-keygen`/PATH 호출 제거, 70-test evidence |
| FS23-P1-010 | canonical `product-verify-supplychain`의 GitHub `actions/attest` + consumer signer check | 단일 서명 권위로 구현, hosted main run 미실행 |
| FS23-P1-011 | safe source builder and no-git verifier | deterministic archive와 nested payload 직접 검증 |
| FS23-P1-012 | Tauri `ReplaceFileW`/no-replace move | 실제 소스 구현, Windows compile/E2E 미실행 |
| FS23-P1-013 | exact dialog path, extension mismatch | 실제 소스 구현·web contract pass, native 실행 미실행 |
| FS23-P1-014 | Vitest 4 clean run | 338 pass, process exit 정상 |
| FS23-P1-015 | npm lock update, audit, CycloneDX | advisory 0, context-bound SBOM |
| FS23-P1-016 | production BUILD_CONTEXT only | missing context build fail, production build pass |
| FS23-P1-017 | safe archive Git object proof | commit/tree/blob/SHA-256 직접 결속 |
| FS23-P1-018 | CycloneDX dependency graph + context digest | source identity와 build context 결속 |
| FS23-P1-019 | full action SHA pins | v2.5 workflow static 검증 |
| FS23-P1-020 | existing CORS capability boundary | 실제 browser/signed app 미실행으로 OPEN |
| FS23-P1-021 | canonical trust module and replaced verifier | 병렬 authority 없이 기존 verifier 교체 |
| FS23-P2-022 | completion schema and bundle verifier | false/NOT_RUN을 PASS로 승격하지 않음 |

`accounting_review/**` 변경 파일은 0개이며 runtime activation은 계속 0이다.
