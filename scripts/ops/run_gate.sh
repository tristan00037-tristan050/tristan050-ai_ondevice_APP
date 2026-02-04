#!/usr/bin/env bash
set -euo pipefail

# meta-only scope proof
echo "PWD=$(pwd)"
echo "TOPLEVEL=$(git rev-parse --show-toplevel 2>/dev/null || echo unknown)"

# Fail-Closed: must be in a git repo
git rev-parse --show-toplevel >/dev/null

# Usage: run_gate.sh "<command>"
CMD="${1:?missing command}"
bash -lc "$CMD"
