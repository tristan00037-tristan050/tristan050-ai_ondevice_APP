#!/bin/bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
OUTPUT="${1:-}"
EVIDENCE="${2:-}"
ROUND5_PROBE="${3:-}"
ROUND6_PROBE="${4:-}"
ROUND7_TYPE_PROBE="${5:-}"
ROUND7_XML_PROBE="${6:-}"
MUTATION_RESULTS="${7:-}"
FINAL_MATRIX_DIR="${8:-}"
ROUND5_PROBE_SHA256="054ceceb6426fd420a387d9474b4667efad34606c86af8f874f83fe1e1a70de8"
ROUND6_PROBE_SHA256="8858a40d21019b8e002e91f2409e76d2724cf3ec3afb48fb8e1a42efee07a7c7"
ROUND7_TYPE_PROBE_SHA256="d6a56e975db6c002a1650766a8862dfaaef954456aac265e96c11e5ed0510648"
ROUND7_XML_PROBE_SHA256="00fd8a411cc877b090421d51575da98bbbe32a81d2a7ef890f87f46daffe0c5b"
ROUND7_HEAD="3f82ca194021248b01d607204cba3af9d6170935"

fail() {
  printf '{"ac23_package":0,"error_code":"%s"}\n' "$1" >&2
  exit 1
}

[[ -n "$OUTPUT" && -n "$EVIDENCE" && -n "$ROUND5_PROBE" && -n "$ROUND6_PROBE" && -n "$ROUND7_TYPE_PROBE" && -n "$ROUND7_XML_PROBE" && -n "$MUTATION_RESULTS" && -n "$FINAL_MATRIX_DIR" ]] || fail E_ARGUMENT
[[ -d "$EVIDENCE" && ! -L "$EVIDENCE" ]] || fail E_EVIDENCE
[[ -f "$ROUND5_PROBE" && ! -L "$ROUND5_PROBE" ]] || fail E_AUDIT_PROBE
[[ -f "$ROUND6_PROBE" && ! -L "$ROUND6_PROBE" ]] || fail E_AUDIT_PROBE
[[ -f "$ROUND7_TYPE_PROBE" && ! -L "$ROUND7_TYPE_PROBE" ]] || fail E_AUDIT_PROBE
[[ -f "$ROUND7_XML_PROBE" && ! -L "$ROUND7_XML_PROBE" ]] || fail E_AUDIT_PROBE
[[ "$(shasum -a 256 "$ROUND5_PROBE" | awk '{print $1}')" == "$ROUND5_PROBE_SHA256" ]] \
  || fail E_AUDIT_PROBE_DIGEST
[[ "$(shasum -a 256 "$ROUND6_PROBE" | awk '{print $1}')" == "$ROUND6_PROBE_SHA256" ]] \
  || fail E_AUDIT_PROBE_DIGEST
[[ "$(shasum -a 256 "$ROUND7_TYPE_PROBE" | awk '{print $1}')" == "$ROUND7_TYPE_PROBE_SHA256" ]] \
  || fail E_AUDIT_PROBE_DIGEST
[[ "$(shasum -a 256 "$ROUND7_XML_PROBE" | awk '{print $1}')" == "$ROUND7_XML_PROBE_SHA256" ]] \
  || fail E_AUDIT_PROBE_DIGEST
[[ -z "$(git -C "$ROOT" status --porcelain=v1 --untracked-files=all)" ]] \
  || fail E_CLEAN_STATUS

HEAD_COMMIT="$(git -C "$ROOT" rev-parse --verify 'HEAD^{commit}')"
HEAD_TREE="$(git -C "$ROOT" show -s --format=%T "$HEAD_COMMIT")"
[[ "$(git -C "$ROOT" show -s --format=%P "$HEAD_COMMIT")" == "$ROUND7_HEAD" ]] \
  || fail E_HEAD_PARENT
[[ "$(git -C "$ROOT" rev-parse "$HEAD_COMMIT^{tree}")" == "$HEAD_TREE" ]] \
  || fail E_HEAD_TREE

mkdir -p "$(dirname "$OUTPUT")"
WORK_PARENT="$(cd "$(dirname "$OUTPUT")" && pwd)"
BUTLER_APP_DATA_DIR="$(mktemp -d "$WORK_PARENT/ac23-parser-appdata.XXXXXX")"
export BUTLER_APP_DATA_DIR
trap 'rm -rf "$BUTLER_APP_DATA_DIR"' EXIT
PYTHONDONTWRITEBYTECODE=1 python3 -m pytest -q --disable-warnings \
  "$ROOT/tests/ac23/test_junit_closed_profile.py" >/dev/null \
  || fail E_JUNIT_PROFILE_TEST

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

run_probe() {
  local probe="$1"
  local family="$2"
  local probe_out probe_err probe_exit
  probe_out="$(mktemp "$WORK_PARENT/ac23-probe.XXXXXX")"
  probe_err="$(mktemp "$WORK_PARENT/ac23-probe.XXXXXX")"
  set +e
  TMPDIR="$WORK_PARENT" TEMP="$WORK_PARENT" TMP="$WORK_PARENT" \
    PYTHONDONTWRITEBYTECODE=1 python3 "$probe" "$OUTPUT" >"$probe_out" 2>"$probe_err"
  probe_exit=$?
  set -e
  [[ "$probe_exit" -ne 0 ]] || fail E_AUDIT_FALSE_PASS
  grep -Eq '^VERIFIER_EXIT=[1-9][0-9]*$' "$probe_out" || fail E_AUDIT_FALSE_PASS
  ! grep -q 'AC23_PASS=YES' "$probe_out" || fail E_AUDIT_FALSE_PASS
  if [[ -n "$family" ]]; then
    grep -q "$family" "$probe_out" || fail E_AUDIT_ERROR_FAMILY
  fi
  rm -f "$probe_out" "$probe_err"
  printf '%s' "$probe_exit"
}

ROUND5_EXIT="$(run_probe "$ROUND5_PROBE" '')"
ROUND6_EXIT="$(run_probe "$ROUND6_PROBE" 'E_EVIDENCE_JUNIT')"
ROUND7_TYPE_EXIT="$(run_probe "$ROUND7_TYPE_PROBE" 'E_EVIDENCE_NONZERO_EXIT')"
ROUND7_XML_EXIT="$(run_probe "$ROUND7_XML_PROBE" 'E_EVIDENCE_JUNIT_DECLARATION')"

PYTHONDONTWRITEBYTECODE=1 python3 "$ROOT/tools/ac23/run_ac23_mutations.py" \
  --repo "$ROOT" \
  --package "$OUTPUT" \
  --output "$MUTATION_RESULTS" \
  --policy "$ROOT/tools/ac23/evidence_policy_v3.json" >/dev/null \
  || fail E_MUTATION
PYTHONDONTWRITEBYTECODE=1 python3 "$ROOT/tools/ac23/verify_external_test_evidence.py" \
  --results "$MUTATION_RESULTS" \
  --package "$OUTPUT" \
  --policy "$ROOT/tools/ac23/evidence_policy_v3.json" >/dev/null \
  || fail E_MUTATION_EVIDENCE

PYTHONDONTWRITEBYTECODE=1 python3 "$ROOT/tools/ac23/collect_final_package_matrix.py" collect \
  --repo "$ROOT" \
  --package "$OUTPUT" \
  --output "$FINAL_MATRIX_DIR" \
  --policy "$ROOT/tools/ac23/evidence_policy_v3.json" >/dev/null \
  || fail E_FINAL_PACKAGE_MATRIX
PYTHONDONTWRITEBYTECODE=1 python3 "$ROOT/tools/ac23/collect_final_package_matrix.py" verify \
  --package "$OUTPUT" \
  --evidence "$FINAL_MATRIX_DIR" \
  --policy "$ROOT/tools/ac23/evidence_policy_v3.json" >/dev/null \
  || fail E_FINAL_PACKAGE_MATRIX

FRESH_ROOT="$(mktemp -d "$WORK_PARENT/ac23-fresh.XXXXXX")"
cp -R "$OUTPUT" "$FRESH_ROOT/AC23_FINAL"
(
  cd "$FRESH_ROOT/AC23_FINAL"
  shasum -a 256 -c SHA256SUMS.txt >/dev/null
  PYTHONDONTWRITEBYTECODE=1 python3 VERIFY/verify_candidate_artifact_identity.py . >/dev/null
) || fail E_FRESH_EXTRACTION
rm -rf "$FRESH_ROOT"

printf '{"ac23_package":1,"error_code":""}\n'
printf 'HEAD_COMMIT=%s\nHEAD_TREE=%s\n' "$HEAD_COMMIT" "$HEAD_TREE"
printf 'ROUND5_PROBE_EXIT=%s\nROUND6_PROBE_EXIT=%s\n' "$ROUND5_EXIT" "$ROUND6_EXIT"
printf 'ROUND7_TYPE_PROBE_EXIT=%s\nROUND7_XML_PROBE_EXIT=%s\n' "$ROUND7_TYPE_EXIT" "$ROUND7_XML_EXIT"
