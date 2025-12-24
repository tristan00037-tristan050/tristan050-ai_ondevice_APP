#!/usr/bin/env bash
set -euo pipefail

# 공통: 응답 바디 디버그 시 유출 방지용 sentinel redaction
HTTP_GATE_REDACT_SENTINEL="${HTTP_GATE_REDACT_SENTINEL:-SHOULD_BLOCK}"
HTTP_GATE_BODY_MAX_BYTES="${HTTP_GATE_BODY_MAX_BYTES:-4096}"

http_gate_request() {
  local method="$1"; shift
  local url="$1"; shift
  local body_out="$1"; shift
  local hdr_out="$1"; shift
  local data="${1:-}"; shift || true

  local err_out
  err_out="$(mktemp -t http_gate_err.XXXXXX)"

  # NOTE: --fail 쓰지 않음(400/403도 정상적으로 바디/코드 확인해야 함)
  local code=""
  if [ -n "$data" ]; then
    code="$(curl -sS -X "$method" "$url" \
      -H "Content-Type: application/json" \
      -D "$hdr_out" -o "$body_out" \
      -w "%{http_code}" \
      --data "$data" \
      "$@" 2>"$err_out" || true)"
  else
    code="$(curl -sS -X "$method" "$url" \
      -D "$hdr_out" -o "$body_out" \
      -w "%{http_code}" \
      "$@" 2>"$err_out" || true)"
  fi

  # curl 자체 실패(네트워크/연결)면 http_code가 비어있을 수 있음 → 000 처리
  if [ -z "$code" ]; then
    echo "000" > "$body_out"
    echo "000"
    rm -f "$err_out"
    return 0
  fi

  rm -f "$err_out"
  echo "$code"
}

http_gate_dump_body() {
  local body_file="$1"
  if [ ! -f "$body_file" ]; then
    echo "(no body file)"
    return 0
  fi

  # 바디를 그대로 찍지 않고, sentinel redaction + 크기 제한
  head -c "${HTTP_GATE_BODY_MAX_BYTES}" "$body_file" \
    | sed "s/${HTTP_GATE_REDACT_SENTINEL}/<REDACTED>/g"
  echo
}

http_gate_expect_code() {
  local name="$1"; shift
  local got="$1"; shift
  local want="$1"; shift
  local body_file="$1"; shift

  if [ "$got" != "$want" ]; then
    echo "[FAIL] $name: want=$want got=$got"
    echo "[FAIL] body (redacted, max ${HTTP_GATE_BODY_MAX_BYTES} bytes):"
    http_gate_dump_body "$body_file"
    return 1
  fi
  echo "[OK] $name: $got"
  return 0
}

