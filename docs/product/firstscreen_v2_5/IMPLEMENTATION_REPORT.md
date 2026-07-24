STATUS=BLOCKED

# Butler FirstScreen v2.5 제품 구현 보고서

이 변경은 복구·검증된 FirstScreen v2.3 Git tree를 기준으로 실제 제품 저장소의 신뢰 검증,
릴리스 provenance, Vite production identity, Tauri native export, CI gate를 직접 교정했다.
별도 데모 앱이나 테스트 전용 성공 경로를 제품 완료의 근거로 사용하지 않는다.

## 구현된 제품 경로

- `butler_pc_core.firstscreen_trust`가 strict JSON, canonical bytes, domain-separated in-process
  Ed25519, 역할별 threshold, 이중 root rotation, signed revocation anti-rollback, 제한·만료 가능한
  risk decision, 네 artifact release subjects를 단일 권위로 검증한다.
- 기존 `verify_storage_risk_acceptance.py`는 `ssh-keygen`/PATH subprocess를 제거하고 위 제품
  권위를 호출한다. bootstrap은 검증 대상 bundle이 아니라 signed app, protected CI 또는 별도
  offline consumer가 제공해야 한다.
- production Vite build는 clean Git에서 생성된 `BUILD_CONTEXT.json`만 읽는다. 누락·짧은 SHA·
  `dev`/`unknown`·schema drift에는 빌드가 즉시 실패하며 context digest가 실제 web bytes와
  설정 화면에 결속된다.
- source archive, Web Dist, SBOM, build context는 같은 commit/tree/context digest에 결속된다.
  signed native artifact와 owner release signature가 없으면 `RELEASE_SUBJECTS`를 만들지 않는다.
- 실제 Tauri `save_export_file`은 dialog 이후 경로를 바꾸지 않는다. extension mismatch를 거부하고,
  64 MiB 상한, CSPRNG temp, 0600, file sync, Windows `ReplaceFileW`, Unix same-filesystem atomic
  publish, parent sync, symlink/reparse guard, concurrent-change 확인을 적용한다.
- GitHub Actions는 full-SHA action pin, hash-locked Python, `npm ci`, npm audit, TypeScript/Vitest,
  production web build, macOS·Windows Rust compile/test, repo-wide regression, consumer attestation
  검증을 하나의 v2.5 gate에 둔다.

## 로컬 검증 결과

- FirstScreen v2.5 변경 범위: 75 pass, 0 fail, 0 error, branch-inclusive coverage 85.76%.
- Butler Desktop Vitest: 338 pass, 0 fail.
- TypeScript `tsc --noEmit`: pass.
- npm audit: production과 전체 lock graph 모두 critical/high/moderate/low 0.
- 저장소 전체: 3,130 pass, 82 fail, 0 error, 32 skip. 따라서 integration pass가 아니다.
- one-command repository contract: canonical base ref 부재로 `BASE_REF_UNAVAILABLE` fail-closed.

85.76% aggregate coverage는 최소 85%를 넘지만, 지시서가 요구한 모든 보안·데이터손실 decision
branch 100%와 mutation 90%를 입증하지 못했다. Rust toolchain이 이 실행 환경에 없어 native 코드는
macOS/Windows에서 컴파일·실행되지 않았다. 이 두 사실 때문에 `FIRSTSCREEN_COMPONENT_PASS=false`다.

## 출시 차단 상태

canonical remote/PR/required CI, 2-of-3 root ceremony, owner risk/release signature, signed/notarized
macOS artifact, Keychain continuity, real-sidecar browser E2E, VoiceOver, Windows 실기기 export,
Apple M3 Metal·memory·thermal·power 측정은 실행되지 않았다. 따라서 `CODE_PASS=false`,
`MERGE_READY=false`, `PRODUCT_RELEASE_READY=false`, `RUNTIME_ACTIVATION_ALLOWED=0`이다.
