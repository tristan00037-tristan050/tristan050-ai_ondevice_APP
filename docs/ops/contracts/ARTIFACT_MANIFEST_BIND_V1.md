# Artifact Manifest Bind V1

ARTIFACT_MANIFEST_BIND_V1_TOKEN=1

## Contract

- **ARTIFACT_MANIFEST_BIND_ENFORCE=1** 일 때만 artifact-manifest binding 검사를 강제한다.
- manifest 파일 존재를 요구한다.
- artifact digest/sha 필드 존재를 요구한다.
- manifest와 artifact 경로 또는 digest/sha 정합이 맞아야 한다.
- 실패 시 **ERROR_CODE**만 출력(meta-only), 원문 0, fail-closed.

## ENFORCE-only / meta-only / fail-closed

- ENFORCE=1에서만 검사 수행. 미설정 또는 0이면 SKIP.
- 출력은 meta-only(키/에러코드만). 원문·전체 JSON dump 출력 0.
- 검증 불가/결측 시 통과 금지(exit 1).

## DoD (add-only)

- **ARTIFACT_MANIFEST_BIND_POLICY_V1_OK=1**: 본 계약(SSOT) 준수 시 1.
- **ARTIFACT_MANIFEST_PRESENT_OK=1**: manifest 파일 존재 시 1.
- **ARTIFACT_MANIFEST_DIGEST_MATCH_OK=1**: manifest와 digest/sha 정합 일치 시 1.

## 경로 예시 (권장 기본값)

ARTIFACT_MANIFEST_PATH=out/ops/artifacts/manifest.json
ARTIFACT_DIGEST_PATH=out/ops/artifacts/digest.json
