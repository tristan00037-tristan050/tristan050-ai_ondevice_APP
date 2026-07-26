# FirstScreen attestation fixture

`attestation_bundle_65c93d9e.json` 은 **실제 `actions/attest` 가 만든 sigstore bundle** 이다.
손으로 만든 값이 아니다.

| 항목 | 값 |
|---|---|
| commit | `65c93d9e675fbd7781185169ba994a9ac57d206e` |
| workflow run | [30183247122](https://github.com/tristan00037-tristan050/tristan050-ai_ondevice_APP/actions/runs/30183247122) |
| subject | `source.zip` · `sha256:dc0cc81511a91473bed318c50e87087feb181bd00d18d1d72f608f8fcedd4cd4` |
| predicate | `https://cyclonedx.org/bom` |
| signer workflow | `.github/workflows/product-verify-supplychain.yml@refs/heads/main` |

가져온 방법:

```bash
gh api "repos/<owner>/<repo>/attestations/sha256:dc0cc815...4cd4" \
  --jq '.attestations[0].bundle' > attestation_bundle_65c93d9e.json
```

subject 인 `source.zip` 은 15MB 라 저장소에 두지 않는다. 시험이 필요할 때
`scripts/release/build_safe_source_archive.py --commit 65c93d9e... --scope-baseline 65c93d9e...^`
로 **결정적으로 재생성**하고, sha256 이 위 subject 와 같은지 먼저 확인한다.

이 fixture 를 쓰는 시험: `tests/firstscreen_v2_5/test_attestation_verification.py`

`gh` 또는 신뢰 루트를 사용할 수 없는 로컬 비게이팅 환경에서만
`BUTLER_ATTESTATION_NON_GATING=1`로 통합 검증을 명시적으로 생략할 수 있다.
GitHub Actions에서는 이 값이 있어도 검증 실패를 건너뛰지 않는다.
