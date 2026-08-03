#!/bin/bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
OUTPUT="${1:-}"
EVIDENCE="${2:-}"
AUDIT_PROBE="${3:-}"
AUDIT_PROBE_SHA256="054ceceb6426fd420a387d9474b4667efad34606c86af8f874f83fe1e1a70de8"

fail() {
  printf '{"ac23_package":0,"error_code":"%s"}\n' "$1" >&2
  exit 1
}

[[ -n "$OUTPUT" && -n "$EVIDENCE" && -n "$AUDIT_PROBE" ]] || fail E_ARGUMENT
[[ -d "$EVIDENCE" && ! -L "$EVIDENCE" ]] || fail E_EVIDENCE
[[ -f "$AUDIT_PROBE" && ! -L "$AUDIT_PROBE" ]] || fail E_AUDIT_PROBE
[[ "$(shasum -a 256 "$AUDIT_PROBE" | awk '{print $1}')" == "$AUDIT_PROBE_SHA256" ]] \
  || fail E_AUDIT_PROBE_DIGEST
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

PROBE_OUT="$(mktemp "${TMPDIR:-/tmp}/ac23-probe.XXXXXX")"
PROBE_ERR="$(mktemp "${TMPDIR:-/tmp}/ac23-probe.XXXXXX")"
trap 'rm -f "$PROBE_OUT" "$PROBE_ERR"' EXIT
set +e
PYTHONDONTWRITEBYTECODE=1 python3 "$AUDIT_PROBE" "$OUTPUT" >"$PROBE_OUT" 2>"$PROBE_ERR"
PROBE_EXIT=$?
set -e
[[ "$PROBE_EXIT" -ne 0 ]] || fail E_AUDIT_FALSE_PASS
grep -Eq '^VERIFIER_EXIT=[1-9][0-9]*$' "$PROBE_OUT" || fail E_AUDIT_FALSE_PASS
! grep -q 'AC23_PASS=YES' "$PROBE_OUT" || fail E_AUDIT_FALSE_PASS

printf '{"ac23_package":1,"error_code":""}\n'
printf 'HEAD_COMMIT=%s\nHEAD_TREE=%s\n' "$HEAD_COMMIT" "$HEAD_TREE"
printf 'AUDIT_PROBE_EXIT=%s\n' "$PROBE_EXIT"
