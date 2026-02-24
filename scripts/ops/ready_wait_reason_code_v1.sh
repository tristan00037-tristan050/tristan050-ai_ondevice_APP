#!/usr/bin/env bash
# PR-P0-DEPLOY-04: Ready wait with status/reason codes (meta-only). Fail-fast on container exit.
# Output: key=value only. No response body or secrets.
set -euo pipefail

READY_WAIT_URL="${READY_WAIT_URL:-http://127.0.0.1:8081/readyz}"
READY_WAIT_TIMEOUT_SEC="${READY_WAIT_TIMEOUT_SEC:-30}"
READY_WAIT_INTERVAL_SEC="${READY_WAIT_INTERVAL_SEC:-2}"
READY_WAIT_CONTAINER_NAME="${READY_WAIT_CONTAINER_NAME:-bff}"
READY_WAIT_LOG="/tmp/ready_wait_v1.log"

ready_wait_http_status="000"
ready_wait_reason_code="<none>"
ready_wait_attempts=0
ready_wait_fail_class="unknown"
ready_wait_fail_hint=""
ready_wait_container_state="unknown"
start_ms=0
end_ms=0

# Ensure log path exists and is writable
: > "$READY_WAIT_LOG"

get_container_state() {
  docker inspect --format '{{.State.Status}}' "$READY_WAIT_CONTAINER_NAME" 2>/dev/null || echo "unknown"
}

get_elapsed_ms() {
  if [[ -n "${start_ms:-}" ]] && [[ "${end_ms:-0}" -ge "${start_ms:-0}" ]]; then
    echo $(( end_ms - start_ms ))
  else
    echo 0
  fi
}

emit() {
  local exit_code="${1:-1}"
  echo "ready_wait_exit_code=$exit_code"
  echo "ready_wait_fail_class=${ready_wait_fail_class}"
  echo "ready_wait_fail_hint=${ready_wait_fail_hint}"
  echo "ready_wait_url=$READY_WAIT_URL"
  echo "ready_wait_http_status=$ready_wait_http_status"
  echo "ready_wait_reason_code=$ready_wait_reason_code"
  echo "ready_wait_attempts=$ready_wait_attempts"
  echo "ready_wait_elapsed_ms=$(get_elapsed_ms)"
  echo "ready_wait_log_tail_path=$READY_WAIT_LOG"
  echo "ready_wait_container_name=$READY_WAIT_CONTAINER_NAME"
  echo "ready_wait_container_state=$ready_wait_container_state"
}

poll_once() {
  local body_file
  body_file="$(mktemp)"
  trap "rm -f '$body_file'" RETURN
  ready_wait_container_state="$(get_container_state)"
  if [[ "$ready_wait_container_state" = "exited" ]]; then
    ready_wait_fail_class="container_exited"
    ready_wait_fail_hint="container $READY_WAIT_CONTAINER_NAME exited"
    return 1
  fi
  local status
  status="$(curl -s -o "$body_file" -w "%{http_code}" --max-time 5 "$READY_WAIT_URL" 2>/dev/null)" || true
  if [[ -z "$status" ]]; then
    status="000"
    ready_wait_fail_class="conn_refused"
    ready_wait_fail_hint="curl failed"
  fi
  ready_wait_http_status="$status"
  ready_wait_reason_code="<none>"
  if [[ -s "$body_file" ]]; then
    local code
    code="$(node -e "
      try {
        const j = JSON.parse(require('fs').readFileSync(process.argv[1], 'utf8'));
        if (j && typeof j.reason_code !== 'undefined') console.log(String(j.reason_code));
      } catch (_) {}
    " "$body_file" 2>/dev/null)" || true
    [[ -n "$code" ]] && ready_wait_reason_code="$code"
  fi
  echo "attempt=$ready_wait_attempts status=$ready_wait_http_status reason_code=$ready_wait_reason_code container_state=$ready_wait_container_state" >> "$READY_WAIT_LOG"
  if [[ "$ready_wait_http_status" = "200" ]]; then
    return 0
  fi
  if [[ "$ready_wait_http_status" = "503" ]]; then
    ready_wait_fail_class="http_503"
    ready_wait_fail_hint="service unavailable"
  elif [[ "$ready_wait_http_status" = "404" ]]; then
    ready_wait_fail_class="http_404"
    ready_wait_fail_hint="not found"
  elif [[ "$ready_wait_http_status" = "000" ]]; then
    ready_wait_fail_class="${ready_wait_fail_class:-conn_refused}"
  fi
  return 1
}

start_sec=$(date +%s 2>/dev/null || echo 0)
start_ms=$(( start_sec * 1000 ))
deadline=$(( start_sec + READY_WAIT_TIMEOUT_SEC ))
ready_wait_attempts=0

while true; do
  ready_wait_attempts=$(( ready_wait_attempts + 1 ))
  end_ms=$(date +%s 2>/dev/null || echo 0)
  end_ms=$(( end_ms * 1000 ))
  if poll_once; then
    ready_wait_container_state="$(get_container_state)"
    emit 0
    exit 0
  fi
  if [[ "$ready_wait_container_state" = "exited" ]]; then
    end_sec=$(date +%s 2>/dev/null || echo 0)
    end_ms=$(( end_sec * 1000 ))
    emit 1
    exit 1
  fi
  now=$(date +%s 2>/dev/null || echo 0)
  if [[ "$now" -ge "$deadline" ]]; then
    ready_wait_fail_class="timeout"
    ready_wait_fail_hint="ready wait timeout ${READY_WAIT_TIMEOUT_SEC}s"
    end_sec=$(date +%s 2>/dev/null || echo 0)
    end_ms=$(( end_sec * 1000 ))
    emit 1
    exit 1
  fi
  sleep "$READY_WAIT_INTERVAL_SEC"
done
