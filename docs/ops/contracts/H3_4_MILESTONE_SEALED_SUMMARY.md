# Hardening++ / Milestone 3.4 — SEALED Summary SSOT (H3.4)

본 문서는 Hardening++ / Milestone 3.4에서 추가/강화된 "운영급 재발 방지 장치"를 단일 정본(SSOT)으로 고정합니다.
원칙: Fail-Closed / output-based DoD / required checks 안정성 / placeholder 0

---

## 0) 최종 상태(판정)
Status: SEALED (H3.4)

의미:
- 레포 전역 가드(repo-guards)로 "규율 위반/재발 경로"를 자동 차단
- 공급망(supplychain)은 최소 provenance + DSSE attestation 검증으로 신뢰 체인 강화
- 업데이트(update)는 max_seen_version 영속 + 원자 갱신으로 anti-rollback을 재부팅 이후에도 강제
- 스토어(store)는 실 DB 어댑터(sql.js)로 확장하되 계약 테스트 100% 유지

---

## 1) Required checks(컨텍스트 단일화)
SSOT:
- docs/ops/contracts/REQUIRED_CHECK_CONTEXTS_SSOT.json
  - supplychain required check 컨텍스트는 정확히 1개:
    - product-verify-supplychain

Enforced by:
- scripts/verify/verify_required_check_context_ssot_single.sh
  - REQUIRED_CHECK_CONTEXT_SINGLE_OK=1

---

## 2) H3.4 구성 요소(워크플로/verify/DoD)

### 2-1) Repo-wide guards (H3.4-prep)
Workflow:
- .github/workflows/product-verify-repo-guards.yml
  - pull_request + merge_group + workflow_dispatch

Runner:
- scripts/verify/verify_repo_contracts.sh

DoD (output keys) — 모두 1이어야 함:
- 기존(레포 공통 가드)
  - OK_CONTAMINATION_REPO_GUARD_OK=1
  - REQUIRED_CHECK_MERGE_GROUP_COVERAGE_OK=1
  - SSOT_PLACEHOLDER_GUARD_OK=1
  - REQUIRED_CHECK_NAME_STABILITY_OK=1
  - REQUIRED_CHECK_NO_SKIPPED_BYPASS_OK=1
  - NO_LOG_GREP_VERDICT_OK=1
  - NO_NPM_INSTALL_FALLBACK_OK=1
  - CANONICALIZE_SHARED_SINGLE_SOURCE_OK=1
- H3.4-prep 신규(재발 3종 봉인)
  - LOCKFILES_TRACKED_OK=1
  - REQUIRED_CHECK_CONTEXT_SINGLE_OK=1
  - AUDIT_APPEND_NO_DRIFT_OK=1
  - COUNTERS_NO_DRIFT_OK=1
  - ARTIFACTS_NOT_TRACKED_OK=1

핵심 봉인 포인트:
- lockfile은 "존재"가 아니라 "git tracked"를 강제
- .artifacts는 CI 생성 경로이므로 git tracked를 금지
- supplychain required check 컨텍스트는 SSOT 기준 1개 고정

---

### 2-2) Supplychain (SUPPLYCHAIN-02: DSSE attestation + identity constraint)
Workflow:
- .github/workflows/product-verify-supplychain.yml
  - pull_request + merge_group + workflow_dispatch
  - permissions:
    - contents: read
    - id-token: write
    - attestations: write
    - artifact-metadata: write
  - job env:
    - GH_TOKEN: ${{ github.token }}

A) SLSA provenance min (presence/format/link)
- scripts/verify/verify_slsa_provenance_min.sh

DoD keys:
- SLSA_PROVENANCE_PRESENT_OK=1
- SLSA_PROVENANCE_FORMAT_OK=1
- SLSA_PROVENANCE_LINK_OK=1

B) DSSE provenance attestation verify (fail-closed)
- scripts/verify/verify_slsa_dsse_attestation.sh

DoD keys:
- GH_TOKEN_PRESENT_OK=1
- SLSA_DSSE_ATTESTATION_PRESENT_OK=1
- SLSA_DSSE_ATTESTATION_VERIFY_OK=1
- SLSA_DSSE_ACTOR_IDENTITY_OK=1
- GH_ATTESTATION_VERIFY_STRICT_OK=1

검증 불변 조건:
- GH_TOKEN이 CI에서 누락되면 즉시 FAIL(원인 명확화)
- gh 버전 하한(>= 2.67.x)을 강제
- exit code만 믿지 않고 JSON 정책(type=array, length>=1)으로 fail-closed

---

### 2-3) Update (UPDATE-02: max_seen_version persisted + atomic monotonic bump)
Runtime wiring:
- verify/signature.ts:
  - store 기반 max_seen_version read-only check(검증)
- services/delivery.ts:
  - 성공 경로에서만 enforceAndBumpMaxSeenVersion 호출(영속 갱신)
  - 실패/deny 경로는 갱신 0

Store behavior:
- FileStore:
  - update_states.json에 상태 저장
  - incoming < current → 즉시 FAIL(ANTI_ROLLBACK)
  - incoming == current → 멱등
  - incoming > current → 원자 갱신
- InMemoryDBStore:
  - 동일 계약(패리티)

Verify:
- scripts/verify/verify_update_max_seen_version_persist.sh

DoD keys:
- ANTI_ROLLBACK_PERSISTED_OK=1
- MAX_SEEN_VERSION_MONOTONIC_OK=1
- MAX_SEEN_VERSION_ATOMIC_UPDATE_OK=1
- MAX_SEEN_VERSION_RESTART_SAFE_OK=1

---

### 2-4) Store (STORE-02: real DB adapter + contract parity 100%)
Store backend wiring:
- store/index.ts:
  - REGISTRY_STORE_BACKEND=sqljs 지원
  - resetRegistryStoreForTests() 제공(테스트 격리)

Real DB adapter:
- store/SqlJsDBStore.ts
  - sql.js(WASM) 기반 SQLite
  - tables: models, model_versions, artifacts, release_pointers, update_states
  - flushNow(): tmp→fsync→rename (no partial write)
  - enforceAndBumpMaxSeenVersion(): BEGIN/COMMIT 트랜잭션 기반(rollback fail-closed)

Tests:
- tests/store_contract_parity.test.ts (공통 계약)
- tests/dbstore_real_adapter.test.ts (실어댑터 전용 EVID)

Verify:
- scripts/verify/verify_svr03_store_parity.sh

DoD keys:
- STORE_CONTRACT_TESTS_SHARED_OK=1
- DBSTORE_PARITY_SMOKE_OK=1
- DBSTORE_REAL_ADAPTER_PARITY_OK=1
- DBSTORE_CONCURRENCY_OK=1
- DBSTORE_NO_PARTIAL_WRITE_OK=1

---

## 3) CI에서 반드시 녹색이어야 하는 Required Workflows
- product-verify-repo-guards
- product-verify-supplychain
- product-verify-model-registry

---

## 4) 로컬/CI 재검증 커맨드(출력 기반)
Repo guards:
- bash scripts/verify/verify_repo_contracts.sh

Supplychain:
- CI: product-verify-supplychain (provenance min + DSSE verify)
- 로컬: DSSE verify는 .artifacts/supplychain_subject.txt가 없으면 SKIP(개발 편의)

Update:
- bash scripts/verify/verify_update_max_seen_version_persist.sh

Store:
- bash scripts/verify/verify_svr03_store_parity.sh

---

## 5) 금지/차단 규칙(요약)
- required check 컨텍스트(특히 supplychain)는 SSOT 기준 1개 외 추가/변경 금지
- .artifacts 디렉터리의 git tracked 금지
- lockfile은 git tracked 강제
- placeholder/TODO/PASTE_* 금지
- Fail-Closed 원칙 위반(continue-on-error, skipped 우회) 금지

