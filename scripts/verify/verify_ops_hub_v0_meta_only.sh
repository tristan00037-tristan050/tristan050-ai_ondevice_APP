#!/usr/bin/env bash
set -euo pipefail

OPS_HUB_META_SCHEMA_SSOT_OK=0
OPS_HUB_NO_RAW_TEXT_GUARD_OK=0
OPS_HUB_REPORT_V0_OK=0
OPS_HUB_REPORT_INPUT_META_ONLY_OK=0

cleanup(){
  echo "OPS_HUB_META_SCHEMA_SSOT_OK=${OPS_HUB_META_SCHEMA_SSOT_OK}"
  echo "OPS_HUB_NO_RAW_TEXT_GUARD_OK=${OPS_HUB_NO_RAW_TEXT_GUARD_OK}"
  echo "OPS_HUB_REPORT_V0_OK=${OPS_HUB_REPORT_V0_OK}"
  echo "OPS_HUB_REPORT_INPUT_META_ONLY_OK=${OPS_HUB_REPORT_INPUT_META_ONLY_OK}"
  if [[ "${OPS_HUB_META_SCHEMA_SSOT_OK}" == "1" ]] && \
     [[ "${OPS_HUB_NO_RAW_TEXT_GUARD_OK}" == "1" ]] && \
     [[ "${OPS_HUB_REPORT_V0_OK}" == "1" ]] && \
     [[ "${OPS_HUB_REPORT_INPUT_META_ONLY_OK}" == "1" ]]; then
    exit 0
  fi
  exit 1
}
trap cleanup EXIT

ROOT="$(git rev-parse --show-toplevel)"
cd "$ROOT"

command -v node >/dev/null 2>&1 || { echo "BLOCK: node not found"; exit 1; }
command -v jq >/dev/null 2>&1 || { echo "BLOCK: jq not found"; exit 1; }

SSOT="docs/ops/contracts/OPS_HUB_META_SCHEMA_V0_SSOT.json"

# 1) SSOT 파일 존재 확인
test -s "$SSOT"
SCHEMA_NAME=$(jq -r '.schema_name' "$SSOT")
if [[ "$SCHEMA_NAME" != "OPS_HUB_META_SCHEMA_V0" ]]; then
  echo "BLOCK: SSOT schema_name mismatch: $SCHEMA_NAME"
  exit 1
fi
OPS_HUB_META_SCHEMA_SSOT_OK=1

# 2) 원문 금지 필드 fail-closed 검증
OUTPUT=$(node - <<'NODE'
const fs = require('fs');
const path = require('path');

const ROOT = process.cwd();
const SSOT_PATH = path.join(ROOT, 'docs/ops/contracts/OPS_HUB_META_SCHEMA_V0_SSOT.json');
const ssot = JSON.parse(fs.readFileSync(SSOT_PATH, 'utf8'));

// Test 1: Valid meta-only event (should pass)
const validEvent = {
  status: "ok",
  reason_code: "SUCCESS",
  ts_utc: "2026-01-30T00:00:00Z",
  duration_ms_bucket: 50,
  request_id: "req_123",
  event_type: "api_call",
  component: "gateway",
  outcome: "success"
};

// Test 2: Invalid event with raw text (should fail)
const invalidEvent = {
  status: "ok",
  reason_code: "SUCCESS",
  ts_utc: "2026-01-30T00:00:00Z",
  raw_text: "This is raw text that should be rejected",
  message: "This message field is forbidden"
};

// Validation function
function validateMetaOnly(event, ssot) {
  // Check allowed keys first (wildcard support for count_*)
  const allowedKeys = new Set(ssot.allowed_keys);
  for (const key in event) {
    let isAllowed = false;
    if (allowedKeys.has(key)) {
      isAllowed = true;
    } else if (key.startsWith('count_') && allowedKeys.has('count_*')) {
      isAllowed = true;
    }
    
    if (!isAllowed) {
      return { valid: false, reason: `Key not in allowlist: ${key}` };
    }
  }
  
  // Check forbidden patterns (only for keys not in allowlist, but since we already checked allowlist, this is redundant)
  // However, we still check for forbidden patterns in values (string content)
  for (const key in event) {
    if (typeof event[key] === 'string') {
      const valueLower = event[key].toLowerCase();
      for (const pattern of ssot.forbidden_patterns) {
        if (valueLower.includes(pattern.toLowerCase())) {
          return { valid: false, reason: `Forbidden pattern found in value: ${pattern} in key: ${key}` };
        }
      }
    }
  }
  
  // Check max string length
  for (const key in event) {
    if (typeof event[key] === 'string' && event[key].length > ssot.max_string_len) {
      return { valid: false, reason: `String too long: ${key} (${event[key].length} > ${ssot.max_string_len})` };
    }
  }
  
  return { valid: true };
}

// Test valid event
const validResult = validateMetaOnly(validEvent, ssot);
if (!validResult.valid) {
  console.error(`BLOCK: Valid event rejected: ${validResult.reason}`);
  process.exit(1);
}

// Test invalid event (should fail)
const invalidResult = validateMetaOnly(invalidEvent, ssot);
if (invalidResult.valid) {
  console.error('BLOCK: Invalid event with raw text was accepted (should fail)');
  process.exit(1);
}

console.log('OPS_HUB_NO_RAW_TEXT_GUARD_OK=1');
NODE
)

if [[ $? -ne 0 ]]; then
  echo "$OUTPUT"
  exit 1
fi

if echo "$OUTPUT" | grep -q "OPS_HUB_NO_RAW_TEXT_GUARD_OK=1"; then
  OPS_HUB_NO_RAW_TEXT_GUARD_OK=1
fi

# 3) Meta-only 샘플 이벤트로 report v0 생성
SAMPLE_EVENT=$(mktemp -t ops_hub_sample_XXXXXX.json 2>/dev/null || mktemp /tmp/ops_hub_sample_XXXXXX.json 2>/dev/null || echo "/tmp/ops_hub_sample_$$.json")
rm -f "$SAMPLE_EVENT"
cat > "$SAMPLE_EVENT" <<'EVENT'
{
  "status": "ok",
  "reason_code": "SUCCESS",
  "ts_utc": "2026-01-30T00:00:00Z",
  "duration_ms_bucket": 50,
  "request_id": "req_sample_001",
  "event_type": "api_call",
  "component": "gateway",
  "operation": "three_blocks",
  "outcome": "success",
  "latency_ms": 45,
  "app_version": "1.0.0",
  "model_version": "v1",
  "count_total": 1,
  "count_success": 1
}
EVENT

# Generate report v0
REPORT_OUTPUT=$(mktemp -t ops_hub_report_XXXXXX.json 2>/dev/null || mktemp /tmp/ops_hub_report_XXXXXX.json 2>/dev/null || echo "/tmp/ops_hub_report_$$.json")
rm -f "$REPORT_OUTPUT"

# Create a temporary Node.js script file (use .js for CommonJS)
NODE_SCRIPT=$(mktemp -t ops_hub_node_XXXXXX.js 2>/dev/null || mktemp /tmp/ops_hub_node_XXXXXX.js 2>/dev/null || echo "/tmp/ops_hub_node_$$.js")
cat > "$NODE_SCRIPT" <<'NODE'
const fs = require('fs');
const path = require('path');

const ROOT = process.cwd();
const SSOT_PATH = path.join(ROOT, 'docs/ops/contracts/OPS_HUB_META_SCHEMA_V0_SSOT.json');
const SAMPLE_EVENT_PATH = process.argv[2];
const REPORT_OUTPUT_PATH = process.argv[3];

const ssot = JSON.parse(fs.readFileSync(SSOT_PATH, 'utf8'));
const event = JSON.parse(fs.readFileSync(SAMPLE_EVENT_PATH, 'utf8'));

// Validate input is meta-only
function validateMetaOnly(event, ssot) {
  // Check allowed keys first (wildcard support for count_*)
  const allowedKeys = new Set(ssot.allowed_keys);
  for (const key in event) {
    let isAllowed = false;
    if (allowedKeys.has(key)) {
      isAllowed = true;
    } else if (key.startsWith('count_') && allowedKeys.has('count_*')) {
      isAllowed = true;
    }
    
    if (!isAllowed) {
      throw new Error(`Key not in allowlist: ${key}`);
    }
  }
  
  // Check forbidden patterns in values (string content)
  for (const key in event) {
    if (typeof event[key] === 'string') {
      const valueLower = event[key].toLowerCase();
      for (const pattern of ssot.forbidden_patterns) {
        if (valueLower.includes(pattern.toLowerCase())) {
          throw new Error(`Forbidden pattern in value: ${pattern} in key: ${key}`);
        }
      }
    }
  }
  
  return true;
}

// Validate
validateMetaOnly(event, ssot);

// Generate report v0
const report = {
  schema_name: "OPS_HUB_REPORT_V0",
  generated_at_utc: new Date().toISOString(),
  input_meta_only: true,
  events_processed: 1,
  summary: {
    total_events: 1,
    success_count: event.outcome === "success" ? 1 : 0,
    avg_latency_ms: event.latency_ms || 0,
    components: [event.component || "unknown"]
  },
  events: [event]
};

fs.writeFileSync(REPORT_OUTPUT_PATH, JSON.stringify(report, null, 2) + '\n');

console.log('OPS_HUB_REPORT_V0_OK=1');
console.log('OPS_HUB_REPORT_INPUT_META_ONLY_OK=1');
NODE

# Run Node.js script and capture output
set +e
REPORT_OUT=$(node "$NODE_SCRIPT" "$SAMPLE_EVENT" "$REPORT_OUTPUT" 2>&1)
NODE_RC=$?
set -e

if [[ $NODE_RC -ne 0 ]]; then
  echo "BLOCK: Node.js script failed:"
  echo "$REPORT_OUT"
  exit 1
fi

# Capture output
if echo "$REPORT_OUT" | grep -q "OPS_HUB_REPORT_V0_OK=1"; then
  OPS_HUB_REPORT_V0_OK=1
fi
if echo "$REPORT_OUT" | grep -q "OPS_HUB_REPORT_INPUT_META_ONLY_OK=1"; then
  OPS_HUB_REPORT_INPUT_META_ONLY_OK=1
fi

# Verify report file exists and is valid
if [[ ! -s "$REPORT_OUTPUT" ]]; then
  echo "BLOCK: Report file not created or empty: $REPORT_OUTPUT"
  exit 1
fi

REPORT_SCHEMA=$(jq -r '.schema_name' "$REPORT_OUTPUT" 2>/dev/null || echo "")
if [[ "$REPORT_SCHEMA" != "OPS_HUB_REPORT_V0" ]]; then
  echo "BLOCK: Report schema_name mismatch: $REPORT_SCHEMA (expected: OPS_HUB_REPORT_V0)"
  exit 1
fi

REPORT_INPUT_META=$(jq -r '.input_meta_only' "$REPORT_OUTPUT" 2>/dev/null || echo "")
if [[ "$REPORT_INPUT_META" != "true" ]]; then
  echo "BLOCK: Report input_meta_only is not true: $REPORT_INPUT_META"
  exit 1
fi

# If we got here, both checks passed
OPS_HUB_REPORT_V0_OK=1
OPS_HUB_REPORT_INPUT_META_ONLY_OK=1

# Cleanup
trap "rm -f \"$SAMPLE_EVENT\" \"$REPORT_OUTPUT\" \"$NODE_SCRIPT\"" EXIT

exit 0
