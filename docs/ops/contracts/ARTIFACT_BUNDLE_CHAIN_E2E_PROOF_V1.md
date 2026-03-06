# Artifact Bundle Chain E2E Proof V1

ARTIFACT_BUNDLE_CHAIN_E2E_PROOF_V1_TOKEN=1

## Contract

- **ARTIFACT_BUNDLE_CHAIN_E2E_PROOF_ENFORCE=1** 일 때만 E2E proof 검사를 강제한다.
- artifact bundle 공급망 체인의 E2E proof 산출물이 존재해야 한다.
- proof는 meta-only여야 하며, strict chain 성공 결과를 증빙해야 한다.
- 실패 시 **ERROR_CODE**만 출력(meta-only), 원문 0, fail-closed.

## ENFORCE-only / meta-only / fail-closed

- ENFORCE=1에서만 검사 수행. 미설정 또는 0이면 SKIP.
- 출력은 meta-only(키/에러코드만). 원문·덤프 0.
- 검증 불가/결측 시 통과 금지(exit 1).

## DoD (add-only)

- **ARTIFACT_BUNDLE_CHAIN_E2E_POLICY_V1_OK=1**: 본 계약(SSOT) 준수 시 1.
- **ARTIFACT_BUNDLE_CHAIN_E2E_PROOF_PRESENT_OK=1**: proof 산출물 존재 시 1.
- **ARTIFACT_BUNDLE_CHAIN_E2E_META_ONLY_OK=1**: proof가 meta-only 규율 준수 시 1.

## proof 경로 (권장 기본값)

proof/latest 또는 아래 경로 사용 가능.

ARTIFACT_BUNDLE_CHAIN_E2E_PROOF_PATH=docs/ops/proofs/artifact_bundle_chain_e2e_latest.json

## meta-only 규율

proof JSON은 원문/전체 덤프를 포함하면 안 된다. 허용: result_ts, result, failed_guard, status 등 짧은 메타 키만.
