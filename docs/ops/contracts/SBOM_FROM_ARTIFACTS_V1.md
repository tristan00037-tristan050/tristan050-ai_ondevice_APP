# SBOM From Artifacts V1

SBOM_FROM_ARTIFACTS_V1_TOKEN=1

## Contract

- **SBOM_FROM_ARTIFACTS_ENFORCE=1** 일 때만 artifact 기반 SBOM 검사를 강제한다.
- Artifact 경로 내 SBOM 파일 존재를 요구한다.
- SBOM 파일은 JSON 파싱 가능해야 하며, 최소 필수 키(bomFormat, specVersion, components)가 존재해야 한다.
- 실패 시 **ERROR_CODE**만 출력(meta-only), 원문 0. fail-closed.

## ENFORCE-only / meta-only / fail-closed

- ENFORCE=1에서만 검사 수행. 미설정 또는 0이면 SKIP.
- 출력은 meta-only(키/에러코드만). 원문·덤프 금지.
- 검증 불가/결측 시 통과 금지(exit 1).

## DoD (add-only)

- **SBOM_FROM_ARTIFACTS_POLICY_V1_OK=1**: 본 계약(SSOT) 준수 시 1.
- **SBOM_FROM_ARTIFACTS_PRESENT_OK=1**: artifact 경로에 SBOM 파일이 존재할 때 1.
- **SBOM_FROM_ARTIFACTS_SCHEMA_OK=1**: JSON 파싱 가능 + 최소 필수 키 존재 시 1.

## SBOM_ARTIFACT_PATH

검사 대상 SBOM 파일 경로(레포 루트 기준). 미지정 시 기본값 사용.

SBOM_ARTIFACT_PATH=out/ops/sbom/from_artifacts.cdx.json
