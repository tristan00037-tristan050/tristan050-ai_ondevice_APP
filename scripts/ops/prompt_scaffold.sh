#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'USAGE'
Usage:
  bash scripts/ops/prompt_scaffold.sh --new <path> --lane <R0|R1|R2|R3|R4> --purpose "<one sentence>" --owner "<owner>" [--reviewed "<YYYY-MM-DD>"]
  bash scripts/ops/prompt_scaffold.sh --check <path>
USAGE
}

die() { echo "ERROR: $*" >&2; exit 1; }
is_md_like() { [[ "$1" =~ \.(md|mdc)$ ]]; }
today_utc() { date -u +%F; }

write_file() {
  local path="$1" lane="$2" purpose="$3" owner="$4" reviewed="$5"
  mkdir -p "$(dirname "$path")"
  [[ -e "$path" ]] && die "file already exists: $path"
  is_md_like "$path" || die "unsupported extension (use .md or .mdc): $path"

  cat >"$path" <<EOF
# [${lane}] Prompt

Prompt-Version: 1.0
Owner: ${owner}
Last-Reviewed: ${reviewed}

## Problem Definition
${purpose}

## Scope
### MUST change
- <list exact allowed paths/files>

### MUST NOT change
- <list forbidden paths/files>

## Invariants
- 1 PR = 1 Purpose
- meta-only (no content dumps)
- Fail-Closed (ambiguity => exit 1 + reason_code)
- Output-based DoD only

## Failure Modes (FMEA) & Threat Model
- <failure mode> -> <signal/output> -> <fail-closed action> -> reason_code=<...>

## Implementation Plan
- Step 1: ...
- Step 2: ...
- Output keys (meta-only):
  - <KEY>=<VALUE>
  - <KEY>=<VALUE>

## Verification & Evidence Plan (DoD)
- Local command:
  - <one-liner>
- PASS keys:
  - <KEY>=1
  - <KEY>_ERROR_COUNT=0
- Negative test:
  - <how to intentionally break and confirm fail-closed>

## Rollback
- Revert commit / revert PR
- Impact radius: <single file / single workflow / single rule>

## Reason Codes
- <REASON_CODE_1>
- <REASON_CODE_2>

## References
- <internal SSOT path(s)>
- <external primary source link(s)>
EOF

  echo "OK: created $path"
}

check_file_min() {
  local path="$1"
  [[ -f "$path" ]] || die "file not found: $path"
  is_md_like "$path" || die "unsupported extension: $path"

  local missing=0
  grep -qi '^Prompt-Version:' "$path" || { echo "MISSING: Prompt-Version"; missing=$((missing+1)); }
  grep -qi '^Owner:' "$path" || { echo "MISSING: Owner"; missing=$((missing+1)); }
  grep -qi '^Last-Reviewed:' "$path" || { echo "MISSING: Last-Reviewed"; missing=$((missing+1)); }

  for h in "Problem Definition" "Scope" "Invariants" "Failure Modes" "Implementation Plan" "Verification" "Rollback" "Reason Codes" "References"; do
    grep -Eiq "^[[:space:]]*##[[:space:]]+${h}" "$path" || { echo "MISSING: ## ${h}"; missing=$((missing+1)); }
  done

  awk '
    BEGIN{inref=0; c=0}
    /^[[:space:]]*##[[:space:]]+References/{inref=1; next}
    /^[[:space:]]*##[[:space:]]+/{ if(inref==1){exit} }
    { if(inref==1 && $0 ~ /[^[:space:]]/ ) c++ }
    END{ exit (c>0)?0:1 }
  ' "$path" || { echo "MISSING: References content"; missing=$((missing+1)); }

  if [[ "$missing" -eq 0 ]]; then
    echo "SCAFFOLD_CHECK_OK=1"
    echo "SCAFFOLD_CHECK_ERROR_COUNT=0"
    exit 0
  fi

  echo "SCAFFOLD_CHECK_OK=0"
  echo "SCAFFOLD_CHECK_ERROR_COUNT=$missing"
  exit 1
}

main() {
  [[ $# -ge 1 ]] || { usage; exit 1; }

  if [[ "$1" == "--new" ]]; then
    shift
    local path="" lane="" purpose="" owner="" reviewed=""
    while [[ $# -gt 0 ]]; do
      case "$1" in
        --new) path="$2"; shift 2 ;;
        --lane) lane="$2"; shift 2 ;;
        --purpose) purpose="$2"; shift 2 ;;
        --owner) owner="$2"; shift 2 ;;
        --reviewed) reviewed="$2"; shift 2 ;;
        *) die "unknown arg: $1" ;;
      esac
    done
    [[ -n "$path" && -n "$lane" && -n "$purpose" && -n "$owner" ]] || die "missing required args"
    [[ -n "$reviewed" ]] || reviewed="$(today_utc)"
    write_file "$path" "$lane" "$purpose" "$owner" "$reviewed"
    exit 0
  fi

  if [[ "$1" == "--check" ]]; then
    [[ $# -eq 2 ]] || die "--check <path> required"
    check_file_min "$2"
    exit 0
  fi

  usage
  exit 1
}

main "$@"
