#!/bin/bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
OUTPUT="${1:-}"
EVIDENCE="${2:-}"

fail() {
  printf '{"ac23_package":0,"error_code":"%s"}\n' "$1" >&2
  exit 1
}

[[ -n "$OUTPUT" && -n "$EVIDENCE" ]] || fail E_ARGUMENT
[[ -d "$EVIDENCE" && ! -L "$EVIDENCE" ]] || fail E_EVIDENCE
[[ -z "$(git -C "$ROOT" status --porcelain=v1 --untracked-files=all)" ]] \
  || fail E_CLEAN_STATUS

HEAD_COMMIT="$(git -C "$ROOT" rev-parse --verify 'HEAD^{commit}')"
HEAD_TREE="$(git -C "$ROOT" show -s --format=%T "$HEAD_COMMIT")"
[[ "$(git -C "$ROOT" rev-parse "$HEAD_COMMIT^{tree}")" == "$HEAD_TREE" ]] \
  || fail E_HEAD_TREE

PYTHONDONTWRITEBYTECODE=1 python3 "$ROOT/tools/ac23/build_candidate_artifact_identity.py" \
  --repo "$ROOT" \
  --output "$OUTPUT" \
  --evidence-dir "$EVIDENCE" \
  --repository-url "https://github.com/tristan00037-tristan050/tristan050-ai_ondevice_APP.git" \
  --head-commit "$HEAD_COMMIT"

PYTHONDONTWRITEBYTECODE=1 python3 \
  "$OUTPUT/VERIFY/verify_candidate_artifact_identity.py" \
  "$OUTPUT" \
  --expected-repository-url \
  "https://github.com/tristan00037-tristan050/tristan050-ai_ondevice_APP.git"

(
  cd "$OUTPUT"
  shasum -a 256 -c SHA256SUMS.txt
)

printf '{"ac23_package":1,"error_code":""}\n'
printf 'HEAD_COMMIT=%s\nHEAD_TREE=%s\n' "$HEAD_COMMIT" "$HEAD_TREE"
