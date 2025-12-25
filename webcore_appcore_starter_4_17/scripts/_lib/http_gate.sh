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

  # ✅ S6-S7: 금지키 감지 시 캡처 중단
  # 금지키 패턴 (JSON 키로 사용되는 경우만)
  local BANNED_KEY_PATTERNS='"(prompt|text|body|context|snippet|excerpt|ticket|document|message|content|ragText|ragChunk|ragContext|ragQuery|ragResult|ragSource|errorMessage|errorText|suggestionText|responseText)"\s*:'
  
  # 요청 데이터에 금지키가 포함되어 있으면 캡처 중단
  if [ -n "$data" ]; then
    if echo "$data" | grep -qiE "$BANNED_KEY_PATTERNS" 2>/dev/null; then
      echo "[SKIP] banned key detected in request data, capture aborted" >&2
      echo "000" > "$body_out"
      echo "000"
      rm -f "$err_out"
      return 0
    fi
  fi

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

  # ✅ S6-S7: 응답 바디에 금지키가 포함되어 있으면 캡처 중단
  if [ -f "$body_out" ] && [ -s "$body_out" ]; then
    if grep -qiE "$BANNED_KEY_PATTERNS" "$body_out" 2>/dev/null; then
      echo "[SKIP] banned key detected in response body, capture aborted" >&2
      echo "" > "$body_out"
    fi
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

