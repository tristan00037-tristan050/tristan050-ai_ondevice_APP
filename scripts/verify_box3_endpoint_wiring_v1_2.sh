#!/usr/bin/env bash
set -euo pipefail
ROOT="${1:-.}"

_scan() {
  grep -RInE "$1" "$ROOT" \
    --exclude-dir=.git --exclude-dir=node_modules --exclude-dir=.venv \
    --exclude="verify_box3_endpoint_wiring_v1_2.sh" \
    --exclude="*.md" --exclude="*.txt" --exclude="MANIFEST.json" 2>/dev/null || true
}

STORAGE_HITS="$(_scan "localStorage|sessionStorage|indexedDB")"
test -z "$STORAGE_HITS" && echo "BROWSER_STORAGE_ZERO=true" || { echo "$STORAGE_HITS"; echo "BLOCK_BROWSER_STORAGE"; exit 1; }

NETWORK_HITS="$(_scan "fetch\(|axios\.|XMLHttpRequest|sendBeacon|WebSocket" | grep -v "127.0.0.1:8765" || true)"
test -z "$NETWORK_HITS" && echo "NON_LOCAL_NETWORK_ZERO=true" || { echo "$NETWORK_HITS"; echo "BLOCK_NON_LOCAL_NETWORK"; exit 1; }

CLAIM_HITS="$(_scan "APPROVED_FOR_PRODUCTION|production ready|release ready|PASS_BOX3_REAL[^_A-Z]")"
test -z "$CLAIM_HITS" && echo "FORBIDDEN_CLAIM_ZERO=true" || { echo "$CLAIM_HITS"; echo "BLOCK_FORBIDDEN_CLAIM"; exit 1; }

FLAG_HITS="$(grep -RInE "real_flag|request.*real.*true|ui.*real.*true|approval.*payload" \
  "$ROOT/butler_pc_core/cards/box3/endpoint_wiring.py" "$ROOT/butler_pc_core/sidecar/routes/box3_draft.py" 2>/dev/null || true)"
test -z "$FLAG_HITS" && echo "REQUEST_UI_APPROVAL_FLAG_ZERO=true" || { echo "$FLAG_HITS"; echo "BLOCK_REQUEST_UI_APPROVAL_FLAG"; exit 1; }

ROUTE_HITS="$(grep -RInE "run_box3_real_pipeline\(.*real_model_runner=None|/v1/cards/3/draft/real|@router\.post\(\"/v1/cards/3/draft/real" \
  "$ROOT/butler_pc_core" 2>/dev/null || true)"
test -z "$ROUTE_HITS" && echo "ROUTE_OVERLAY_OLD_HARDCODE_ZERO=true" || { echo "$ROUTE_HITS"; echo "BLOCK_ROUTE_OVERLAY_OR_OLD_HARDCODE"; exit 1; }

LEAK_HITS="$(_scan "/Users/|/home/|/Volumes/|sk-proj-|BEGIN PRIVATE KEY|raw_prompt|raw_reference|raw_draft")"
test -z "$LEAK_HITS" && echo "RAW_PATH_SECRET_LEAK_ZERO=true" || { echo "$LEAK_HITS"; echo "BLOCK_RAW_PATH_SECRET_LEAK"; exit 1; }

BINARY_HITS="$(find "$ROOT" -type f \( -name "*.safetensors" -o -name "*.gguf" -o -name "*.bin" -o -name "*.npy" -o -name "*.pkl" \) 2>/dev/null | grep . || true)"
test -z "$BINARY_HITS" && echo "BINARY_ARTIFACT_ZERO=true" || { echo "$BINARY_HITS"; echo "BLOCK_BINARY_ARTIFACT"; exit 1; }

CLAUDE_HITS="$(grep -RIn "Generated with Claude Code\|Co-Authored-By: Claude" "$ROOT" \
  --exclude-dir=.git --exclude-dir=node_modules --exclude-dir=.venv \
  --exclude="verify_box3_endpoint_wiring_v1_2.sh" 2>/dev/null || true)"
test -z "$CLAUDE_HITS" && echo "CLAUDE_FOOTER_ZERO=true" || { echo "$CLAUDE_HITS"; echo "BLOCK_CLAUDE_FOOTER"; exit 1; }
