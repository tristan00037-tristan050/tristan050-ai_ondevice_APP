#!/usr/bin/env bash
# Remote-First Truth Helper: Check if path exists on origin/main
# Usage: scripts/ops/remote_main_has_path.sh <path>
# Exit codes: 0=PASS (exists), 1=FAIL (not found), 2=usage error

set -euo pipefail

# Fail-Closed: 인자 없으면 exit 2
if [ $# -lt 1 ]; then
  echo "FAIL: usage: $0 <path>" >&2
  exit 2
fi

PATH_ARG="$1"

# Ensure we're in a git repo
ROOT="$(git rev-parse --show-toplevel 2>/dev/null)" || {
  echo "FAIL: not a git repository" >&2
  exit 2
}

# Remote-First Truth: fetch origin/main first
git fetch -q origin main

# Check if path exists on origin/main (meta-only: path only)
if git show "origin/main:${PATH_ARG}" >/dev/null 2>&1; then
  echo "PASS: ${PATH_ARG}"
  exit 0
else
  echo "FAIL: ${PATH_ARG}"
  exit 1
fi

