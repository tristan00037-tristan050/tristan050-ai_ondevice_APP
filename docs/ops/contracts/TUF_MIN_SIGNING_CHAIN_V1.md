# TUF Min Signing Chain V1

TUF_MIN_SIGNING_CHAIN_V1_TOKEN=1

## Contract

- **TUF_MIN_SIGNING_CHAIN_ENFORCE=1** 일 때만 최소 서명 체인(roles / expiry / verify) 검사를 강제한다.
- 키 material은 레포에 넣지 않는다. ENFORCE=1에서만 서명 검증을 강제하며, 로컬은 SKIP 유지 가능.
- 실패는 fail-closed (ERROR_CODE만 출력, 원문0).

## DoD (add-only)

- **TUF_MIN_ROLES_PRESENT_OK=1**: root, targets, snapshot, timestamp 역할 메타데이터 파일 존재.
- **TUF_EXPIRES_ENFORCED_OK=1**: 각 역할 메타데이터에 `signed.expires` 필드 존재(만료 시행).
- **TUF_SIGNATURE_VERIFY_OK=1**: ENFORCE=1에서 서명 구조 검사(또는 검증 수행). 키는 레포 외부(환경 등)에서만 사용.

## TUF_META_ROOT

메타데이터 루트 경로. 미지정 시 `docs/ops/contracts/SECURE_UPDATE_TUF_PRINCIPLES_SSOT_V1.txt`의 TUF_META_ROOT를 참조.

TUF_META_ROOT=out/ops/tuf
