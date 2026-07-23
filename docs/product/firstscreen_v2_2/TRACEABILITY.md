# FirstScreen v2.2 교정 추적표

상태는 실제 제품 소스와 이 환경에서 생성한 원시 증거만을 기준으로 한다. `IMPLEMENTED`는 실행 PASS와 같지 않다.

| 요구 | 제품 반영 | 검증 상태 | 정본 증거 |
|---|---|---|---|
| FS21-P0-005 제목·FTS 위험 | 서명된 위험 수용 결정과 만료·통제·검토 트리거를 저장소에 결속 | LOCAL_PASS | `release_exceptions/`; `verify_storage_risk_acceptance.py` |
| FIX-FS-001 manifest-bound BUILD_INFO | source ZIP에 commit/tree 결속 BUILD_INFO와 독립 tree/blob/archive-mode verifier 포함 | LOCAL_PASS: `.git` 없는 임시 폴더 | `build_safe_source_archive.py`; `verify_source_bundle.py`; `test_safe_source_archive.py` |
| FIX-FS-003 collection 0 error | importlib 수집, `src` 경로, 누락 export 보완, torch 선택 격리 | LOCAL_PASS: 3,166 collection / 0 error | `pytest.ini`; `phase_c_shared.py`; `tests/turboq/` |
| FIX-FS-003 full tests 0 fail | 저장소 전체 required CI를 별도 정본 게이트로 추가 | FAIL: 3,055 pass / 81 fail / 32 skip | workflow; `evidence/pytest-repository-release.xml` |
| 저장소 one-command 계약 | 정본 `verify_repo_contracts.sh`를 keys-only 모드로 실행 | FAIL: `policy headers schema v1` / `FILE_NOT_FOUND` | `evidence/repo-contracts-summary.txt` |
| FIX-FS-006 Playwright·axe·keyboard | 실제 sidecar와 브라우저를 연결하는 첫 화면·폴더·검색·대화·오류·모달·휴지통 시나리오 작성 | NOT_RUN: browser binary unavailable | `butler-desktop/e2e/`; `playwright.config.ts` |
| FIX-FS-006 modal focus | 공용 ModalFrame, initial focus, trap, Escape, 호출자 focus 복귀 | LOCAL_UNIT_PASS | `DeleteConfirmModal.tsx`; `DeleteConfirmAccessibility.test.tsx` |
| P1 sidecar exact origin | relative absolute-path만 허용, credentials/fragment/cross-origin 차단, redirect error | LOCAL_UNIT_PASS | `sidecarFetch.ts`; `SidecarFetchSecurity.test.ts` |
| P1 Tauri browser/filesystem 최소권한 | script unsafe-inline 제거, 외부 font fetch 제거, 재귀 filesystem scope 제거 | LOCAL_UNIT_PASS | `tauri.conf.json`; `capabilities/default.json`; `DesktopSecurityPolicy.test.ts` |
| P1 new-install atomicity | 소유 확인 staging, 프로세스 간 install lock, fsync, atomic publish, 안전 rollback/retry | LOCAL_PASS | `home/store.py`; `test_home_product_store_v2.py` |
| P1 dependencies/provenance | Python hash lock, Node lock, Rust pin, action full SHA, CycloneDX resolved graph | LOCAL_SCHEMA_PASS; HOSTED_ATTEST_NOT_RUN | lock files; workflow; `generate_cyclonedx_sbom.py` |
| P1 critical branch coverage 85% | CI threshold를 85% branch coverage로 강제 | FAIL: 67.34% | workflow; `evidence/coverage-firstscreen-final.xml` |
| P2 replay semantics | 응답 body 불변, `Idempotency-Replayed` header로 최초/재생 구분 | LOCAL_PASS | `home/store.py`; `routes/home.py`; API contract test |
| C: canonical remote/PR/CI/attestation | workflow 정의만 존재 | NOT_RUN | 외부 canonical remote 필요 |
| C: signed macOS/Keychain/VoiceOver | 코드나 정적 aria로 대체하지 않음 | NOT_RUN | macOS 15 arm64 signed .app 필요 |
| 실기기 M3·Metal·memory·thermal·power | 로컬 Linux 결과로 대체하지 않음 | NOT_RUN | 그룹A 실기기 raw evidence 필요 |

따라서 현재 판정은 `CODE_PASS=NO`, `MERGE_READY=NO`, `PRODUCT_RELEASE_READY=NO`, `RUNTIME_ACTIVATION_ALLOWED=0`이다.
