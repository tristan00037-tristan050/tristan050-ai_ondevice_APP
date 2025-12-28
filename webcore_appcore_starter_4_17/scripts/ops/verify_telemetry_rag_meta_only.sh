#!/usr/bin/env bash
set -euo pipefail
cd "$(git rev-parse --show-toplevel)/webcore_appcore_starter_4_17"
exec bash scripts/ops/verify_rag_meta_only.sh

