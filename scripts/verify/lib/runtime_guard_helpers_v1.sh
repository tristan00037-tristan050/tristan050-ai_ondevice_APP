#!/usr/bin/env bash
set -euo pipefail

# --- tool gates (fail-closed) ---
rgv1_require_tools() {
  command -v node >/dev/null 2>&1 || { echo "BLOCK: node not found"; exit 1; }
  command -v curl >/dev/null 2>&1 || { echo "BLOCK: curl not found"; exit 1; }
  command -v jq   >/dev/null 2>&1 || { echo "BLOCK: jq not found"; exit 1; }
}

# --- temp files (no fixed /tmp paths) ---
rgv1_mktemp() {
  mktemp "${1:-/tmp/runtime_guard.XXXXXX}"
}

# --- free port (no /dev/tcp) ---
rgv1_free_port() {
  node -e 'const s=require("net").createServer(); s.listen(0,"127.0.0.1",()=>{console.log(s.address().port); s.close();});'
}

# --- pid-safe cleanup ---
rgv1_kill_pid() {
  local pid="${1:-}"
  if [[ -n "${pid}" ]]; then
    kill "${pid}" >/dev/null 2>&1 || true
  fi
}

# --- wait for marker in log (fail-closed) ---
rgv1_wait_for_log_marker() {
  local file="$1"
  local marker="$2"
  local max="${3:-50}"
  for _ in $(seq 1 "${max}"); do
    if [[ -f "${file}" ]] && grep -q "${marker}" "${file}" 2>/dev/null; then
      return 0
    fi
    sleep 0.1
  done
  echo "BLOCK: marker '${marker}' not found in ${file}"
  return 1
}

