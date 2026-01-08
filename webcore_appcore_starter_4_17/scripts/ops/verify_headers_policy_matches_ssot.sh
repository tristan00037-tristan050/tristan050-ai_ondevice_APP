#!/usr/bin/env bash
# SSOT-Policy 헤더 정합성 검사 (SSOT v3.4)
# policy/headers.yaml의 필수 헤더가 SSOT v3.4와 1:1로 일치하는지 검증
# Fail-Closed: 불일치 시 즉시 차단

set -euo pipefail

ROOT="$(git rev-parse --show-toplevel 2>/dev/null)" || {
  echo "FAIL: not a git repository" >&2
  exit 2
}

cd "${ROOT}/webcore_appcore_starter_4_17"

POLICY_FILE="policy/headers.yaml"

# SSOT v3.4 정본 헤더 정의 (이 스크립트에 하드코딩)
SSOT_LIVE_HEADERS=("X-Tenant" "X-User-Id" "X-User-Role")
SSOT_EXPORT_HEADERS=("Idempotency-Key" "X-Tenant" "X-User-Id" "X-User-Role")

# 정책 파일 존재 확인
if [ ! -f "${POLICY_FILE}" ]; then
  echo "FAIL: policy file not found: ${POLICY_FILE}" >&2
  exit 1
fi

# Python으로 YAML 파싱 및 헤더 추출 (meta-only)
# 정책 본문을 출력하지 않고 헤더 이름만 추출
# pyyaml 의존성 없이 간단한 파서 사용
EXTRACT_SCRIPT=$(cat <<'PYTHON'
import sys
import json
import re

try:
    with open(sys.argv[1], 'r', encoding='utf-8') as f:
        content = f.read()
    
    result = {}
    current_rule_id = None
    in_required_headers = False
    headers = []
    
    for line in content.split('\n'):
        line_stripped = line.strip()
        if not line_stripped or line_stripped.startswith('#'):
            continue
        
        # rule id 찾기
        if 'id:' in line_stripped and 'header_' in line_stripped:
            # 이전 rule 저장
            if current_rule_id and headers:
                result[current_rule_id] = sorted(headers)
                headers = []
            
            # 새 rule id 추출
            match = re.search(r'id:\s*"([^"]+)"', line_stripped)
            if match:
                current_rule_id = match.group(1)
                in_required_headers = False
            continue
        
        # required_headers 섹션 시작
        if 'required_headers:' in line_stripped:
            in_required_headers = True
            headers = []
            continue
        
        # required_headers 리스트 항목 추출
        if in_required_headers and current_rule_id:
            if line_stripped.startswith('- '):
                header = line_stripped[2:].strip().strip('"').strip("'")
                if header:
                    headers.append(header)
            elif line_stripped and not line_stripped.startswith('-') and not line_stripped.startswith('  '):
                # 리스트가 끝남 (다른 키로 이동)
                in_required_headers = False
    
    # 마지막 rule 저장
    if current_rule_id and headers:
        result[current_rule_id] = sorted(headers)
    
    if not result:
        print(json.dumps({"error": "NO_RULES_FOUND"}))
        sys.exit(1)
    
    print(json.dumps(result))
except Exception as e:
    print(json.dumps({"error": "PARSE_ERROR", "message": str(e)}))
    sys.exit(1)
PYTHON
)

# 정책 파일에서 헤더 추출
POLICY_JSON=$(python3 -c "${EXTRACT_SCRIPT}" "${POLICY_FILE}" 2>&1)

if [ $? -ne 0 ]; then
  echo "FAIL: failed to parse policy file" >&2
  echo "reason_code=PARSE_ERROR" >&2
  exit 1
fi

# JSON 파싱
LIVE_HEADERS_JSON=$(echo "${POLICY_JSON}" | python3 -c "import sys, json; d=json.load(sys.stdin); print(json.dumps(d.get('header_live_required_v3_4', [])))")
EXPORT_HEADERS_JSON=$(echo "${POLICY_JSON}" | python3 -c "import sys, json; d=json.load(sys.stdin); print(json.dumps(d.get('header_export_required_v3_4', [])))")

# Live 헤더 검증
LIVE_HEADERS_ARRAY=$(echo "${LIVE_HEADERS_JSON}" | python3 -c "import sys, json; print(' '.join(sorted(json.load(sys.stdin))))")
SSOT_LIVE_SORTED=$(printf '%s\n' "${SSOT_LIVE_HEADERS[@]}" | sort | tr '\n' ' ' | sed 's/ $//')

if [ "${LIVE_HEADERS_ARRAY}" != "${SSOT_LIVE_SORTED}" ]; then
  echo "FAIL: Live headers mismatch" >&2
  echo "reason_code=LIVE_HEADERS_MISMATCH" >&2
  echo "expected=$(echo ${SSOT_LIVE_SORTED} | tr ' ' ',')" >&2
  echo "actual=$(echo ${LIVE_HEADERS_ARRAY} | tr ' ' ',')" >&2
  exit 1
fi

# Export 헤더 검증
EXPORT_HEADERS_ARRAY=$(echo "${EXPORT_HEADERS_JSON}" | python3 -c "import sys, json; print(' '.join(sorted(json.load(sys.stdin))))")
SSOT_EXPORT_SORTED=$(printf '%s\n' "${SSOT_EXPORT_HEADERS[@]}" | sort | tr '\n' ' ' | sed 's/ $//')

if [ "${EXPORT_HEADERS_ARRAY}" != "${SSOT_EXPORT_SORTED}" ]; then
  echo "FAIL: Export headers mismatch" >&2
  echo "reason_code=EXPORT_HEADERS_MISMATCH" >&2
  echo "expected=$(echo ${SSOT_EXPORT_SORTED} | tr ' ' ',')" >&2
  echo "actual=$(echo ${EXPORT_HEADERS_ARRAY} | tr ' ' ',')" >&2
  exit 1
fi

# PASS
echo "PASS: headers policy matches SSOT v3.4"
echo "live_headers=$(echo ${SSOT_LIVE_SORTED} | tr ' ' ',')"
echo "export_headers=$(echo ${SSOT_EXPORT_SORTED} | tr ' ' ',')"
exit 0
