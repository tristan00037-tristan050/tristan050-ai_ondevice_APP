# Artifact Bundle Verifier Chain V1

ARTIFACT_BUNDLE_VERIFIER_CHAIN_V1_TOKEN=1

## Contract

- **ARTIFACT_BUNDLE_VERIFIER_CHAIN_ENFORCE=1** 일 때만 verifier chain 검사를 강제한다.
- artifact bundle 검증 체인에 필요한 verifier가 모두 verify_repo_contracts.sh에 연결돼 있어야 한다.
- verifier 순서가 고정된 체인 규약과 일치해야 한다.
- 실패 시 **ERROR_CODE**만 출력(meta-only), 원문 0, fail-closed.

## ENFORCE-only / meta-only / fail-closed

- ENFORCE=1에서만 검사 수행. 미설정 또는 0이면 SKIP.
- 출력은 meta-only(키/에러코드만). 원문·덤프 0.
- 검증 불가/결측 시 통과 금지(exit 1).

## DoD (add-only)

- **ARTIFACT_BUNDLE_VERIFIER_CHAIN_POLICY_V1_OK=1**: 본 계약(SSOT) 준수 시 1.
- **ARTIFACT_BUNDLE_VERIFIER_CHAIN_PRESENT_OK=1**: 필수 verifier 5개 모두 연결 시 1.
- **ARTIFACT_BUNDLE_VERIFIER_CHAIN_ORDER_OK=1**: 체인 순서가 규약과 일치 시 1.

## 고정 체인 순서 (add-only)

1. verify_tuf_min_signing_chain_v1.sh
2. verify_sbom_from_artifacts_v1.sh
3. verify_artifact_manifest_bind_v1.sh
4. verify_artifact_bundle_integrity_v1.sh
5. verify_artifact_bundle_provenance_link_v1.sh

ANCHOR_PATH=scripts/verify/verify_repo_contracts.sh
