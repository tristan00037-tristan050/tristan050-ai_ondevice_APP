# Artifact Bundle Provenance Link V1

ARTIFACT_BUNDLE_PROVENANCE_LINK_V1_TOKEN=1

## Contract

- **ARTIFACT_BUNDLE_PROVENANCE_LINK_ENFORCE=1** 일 때만 provenance link 검사를 강제한다.
- provenance(attestation) 파일 존재 필수.
- provenance의 subject digest와 artifact digest가 일치해야 한다.
- provenance가 manifest 또는 bundle 식별자와 연결돼야 한다.
- 실패 시 **ERROR_CODE**만 출력(meta-only), 원문 0, fail-closed.

## ENFORCE-only / meta-only / fail-closed

- ENFORCE=1에서만 검사 수행. 미설정 또는 0이면 SKIP.
- 출력은 meta-only(키/에러코드만). 원문·덤프 0.
- 검증 불가/결측 시 통과 금지(exit 1).

## DoD (add-only)

- **ARTIFACT_BUNDLE_PROVENANCE_POLICY_V1_OK=1**: 본 계약(SSOT) 준수 시 1.
- **ARTIFACT_PROVENANCE_PRESENT_OK=1**: provenance 파일 존재 시 1.
- **ARTIFACT_PROVENANCE_SUBJECT_MATCH_OK=1**: subject digest와 artifact digest 일치 및 manifest/bundle 연결 시 1.

## 경로 예시 (권장 기본값)

ARTIFACT_PROVENANCE_PATH=out/ops/provenance/attestation.json
ARTIFACT_DIGEST_PATH=out/ops/artifacts/digest.json
