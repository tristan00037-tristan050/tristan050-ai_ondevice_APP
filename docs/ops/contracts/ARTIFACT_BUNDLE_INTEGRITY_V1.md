# Artifact Bundle Integrity V1

ARTIFACT_BUNDLE_INTEGRITY_V1_TOKEN=1

## Contract

- **ARTIFACT_BUNDLE_INTEGRITY_ENFORCE=1** 일 때만 artifact bundle integrity 검사를 강제한다.
- bundle 구성 최소 세트(TUF metadata / manifest / digest / SBOM)가 모두 존재해야 한다.
- bundle 내부 참조 경로/sha/digest 정합이 맞아야 한다.
- 실패 시 **ERROR_CODE**만 출력(meta-only), 원문 0, fail-closed.

## ENFORCE-only / meta-only / fail-closed

- ENFORCE=1에서만 검사 수행. 미설정 또는 0이면 SKIP.
- 출력은 meta-only(키/에러코드만). 원문·전체 JSON dump 출력 0.
- 검증 불가/결측 시 통과 금지(exit 1).

## DoD (add-only)

- **ARTIFACT_BUNDLE_INTEGRITY_POLICY_V1_OK=1**: 본 계약(SSOT) 준수 시 1.
- **ARTIFACT_BUNDLE_COMPONENTS_PRESENT_OK=1**: bundle 구성요소 전부 존재 시 1.
- **ARTIFACT_BUNDLE_CROSS_REF_MATCH_OK=1**: manifest ↔ digest, manifest ↔ SBOM 참조/경로 정합 일치 시 1.

## 권장 bundle 구성

TUF_META_ROOT=out/ops/tuf
ARTIFACT_MANIFEST_PATH=out/ops/artifacts/manifest.json
ARTIFACT_DIGEST_PATH=out/ops/artifacts/digest.json
ARTIFACT_SBOM_PATH=out/ops/sbom/from_artifacts.cdx.json
