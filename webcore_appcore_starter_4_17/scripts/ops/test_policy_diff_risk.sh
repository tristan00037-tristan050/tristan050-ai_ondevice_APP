#!/usr/bin/env bash
# Policy Diff Risk Score 테스트 (샘플 diff로 재현)

set -euo pipefail

ROOT="$(git rev-parse --show-toplevel 2>/dev/null)" || {
  echo "FAIL: not a git repository" >&2
  exit 2
}

cd "${ROOT}/webcore_appcore_starter_4_17"

CALC_SCRIPT="scripts/ops/calc_policy_diff_risk.py"

echo "== Policy Diff Risk Score Test =="

# 테스트용 임시 파일
OLD_FILE=$(mktemp)
NEW_FILE=$(mktemp)

# Test 1: 금지 필드 제거 (Risk Score +10)
cat > "${OLD_FILE}" <<'EOF'
version: "1.0"
rules:
  - id: "export_001"
    name: "금지 필드 차단"
    forbidden_fields:
      - "raw_text"
      - "full_content"
      - "token"
    action: "block"
EOF

cat > "${NEW_FILE}" <<'EOF'
version: "1.0"
rules:
  - id: "export_001"
    name: "금지 필드 차단"
    forbidden_fields:
      - "raw_text"
    action: "block"
EOF

echo ""
echo "Test 1: 금지 필드 제거 (예상: RISK_SCORE >= 10)"
RESULT=$(python3 "${CALC_SCRIPT}" "${OLD_FILE}" "${NEW_FILE}")
echo "${RESULT}" | python3 -c "import sys, json; d=json.load(sys.stdin); print(f\"RISK_SCORE={d['RISK_SCORE']}\"); assert d['RISK_SCORE'] >= 10, 'Test 1 failed'"
echo "PASS: Test 1"

# Test 2: max_limit_days 증가 (Risk Score +5)
cat > "${OLD_FILE}" <<'EOF'
version: "1.0"
rules:
  - id: "export_003"
    name: "범위 제한"
    max_limit_days: 90
    action: "block"
EOF

cat > "${NEW_FILE}" <<'EOF'
version: "1.0"
rules:
  - id: "export_003"
    name: "범위 제한"
    max_limit_days: 180
    action: "block"
EOF

echo ""
echo "Test 2: max_limit_days 증가 (예상: RISK_SCORE >= 5)"
RESULT=$(python3 "${CALC_SCRIPT}" "${OLD_FILE}" "${NEW_FILE}")
echo "${RESULT}" | python3 -c "import sys, json; d=json.load(sys.stdin); print(f\"RISK_SCORE={d['RISK_SCORE']}\"); assert d['RISK_SCORE'] >= 5, 'Test 2 failed'"
echo "PASS: Test 2"

# Test 3: action block -> allow (Risk Score +20)
cat > "${OLD_FILE}" <<'EOF'
version: "1.0"
rules:
  - id: "export_001"
    name: "금지 필드 차단"
    action: "block"
EOF

cat > "${NEW_FILE}" <<'EOF'
version: "1.0"
rules:
  - id: "export_001"
    name: "금지 필드 차단"
    action: "allow"
EOF

echo ""
echo "Test 3: action block -> allow (예상: RISK_SCORE >= 20)"
RESULT=$(python3 "${CALC_SCRIPT}" "${OLD_FILE}" "${NEW_FILE}")
echo "${RESULT}" | python3 -c "import sys, json; d=json.load(sys.stdin); print(f\"RISK_SCORE={d['RISK_SCORE']}\"); assert d['RISK_SCORE'] >= 20, 'Test 3 failed'"
echo "PASS: Test 3"

# Test 4: 규칙 제거 (Risk Score +15)
cat > "${OLD_FILE}" <<'EOF'
version: "1.0"
rules:
  - id: "export_001"
    name: "금지 필드 차단"
    action: "block"
  - id: "export_002"
    name: "필수 헤더 검증"
    action: "block"
EOF

cat > "${NEW_FILE}" <<'EOF'
version: "1.0"
rules:
  - id: "export_001"
    name: "금지 필드 차단"
    action: "block"
EOF

echo ""
echo "Test 4: 규칙 제거 (예상: RISK_SCORE >= 15)"
RESULT=$(python3 "${CALC_SCRIPT}" "${OLD_FILE}" "${NEW_FILE}")
echo "${RESULT}" | python3 -c "import sys, json; d=json.load(sys.stdin); print(f\"RISK_SCORE={d['RISK_SCORE']}\"); assert d['RISK_SCORE'] >= 15, 'Test 4 failed'"
echo "PASS: Test 4"

# Test 5: 변경 없음 (Risk Score 0)
cat > "${OLD_FILE}" <<'EOF'
version: "1.0"
rules:
  - id: "export_001"
    name: "금지 필드 차단"
    action: "block"
EOF

cat > "${NEW_FILE}" <<'EOF'
version: "1.0"
rules:
  - id: "export_001"
    name: "금지 필드 차단"
    action: "block"
EOF

echo ""
echo "Test 5: 변경 없음 (예상: RISK_SCORE = 0)"
RESULT=$(python3 "${CALC_SCRIPT}" "${OLD_FILE}" "${NEW_FILE}")
echo "${RESULT}" | python3 -c "import sys, json; d=json.load(sys.stdin); print(f\"RISK_SCORE={d['RISK_SCORE']}\"); assert d['RISK_SCORE'] == 0, 'Test 5 failed'"
echo "PASS: Test 5"

rm -f "${OLD_FILE}" "${NEW_FILE}"

echo ""
echo "== All Tests Passed =="

