# Artifact Bundle Chain Strict Mode V1

ARTIFACT_BUNDLE_CHAIN_STRICT_MODE_V1_TOKEN=1

## Contract

- **ARTIFACT_BUNDLE_CHAIN_STRICT_MODE_ENFORCE=1** 일 때만 strict mode 검사를 강제한다.
- artifact bundle 공급망 체인에 필요한 verifier들이 strict mode에서 모두 ENFORCE=1로 연결돼 있어야 한다.
- strict mode에서는 하나의 실패도 pass로 흘러가면 안 된다.
- 실패 시 **ERROR_CODE**만 출력(meta-only), 원문 0, fail-closed.

## ENFORCE-only / meta-only / fail-closed

- ENFORCE=1에서만 검사 수행. 미설정 또는 0이면 SKIP.
- 출력은 meta-only(키/에러코드만). 원문·덤프 0.
- 검증 불가/결측 시 통과 금지(exit 1).

## DoD (add-only)

- **ARTIFACT_BUNDLE_CHAIN_STRICT_POLICY_V1_OK=1**: 본 계약(SSOT) 준수 시 1.
- **ARTIFACT_BUNDLE_CHAIN_STRICT_ENFORCE_OK=1**: 체인 6개 모두 ENFORCE 변수로 연결 시 1.
- **ARTIFACT_BUNDLE_CHAIN_STRICT_FAILCLOSED_OK=1**: fail-open 패턴 없음 시 1.

## Strict chain 대상 (6개, 순서 고정)

1. verify_tuf_min_signing_chain_v1.sh → TUF_MIN_SIGNING_CHAIN_ENFORCE
2. verify_sbom_from_artifacts_v1.sh → SBOM_FROM_ARTIFACTS_ENFORCE
3. verify_artifact_manifest_bind_v1.sh → ARTIFACT_MANIFEST_BIND_ENFORCE
4. verify_artifact_bundle_integrity_v1.sh → ARTIFACT_BUNDLE_INTEGRITY_ENFORCE
5. verify_artifact_bundle_provenance_link_v1.sh → ARTIFACT_BUNDLE_PROVENANCE_LINK_ENFORCE
6. verify_artifact_bundle_verifier_chain_v1.sh → ARTIFACT_BUNDLE_VERIFIER_CHAIN_ENFORCE

ANCHOR_PATH=scripts/verify/verify_repo_contracts.sh
