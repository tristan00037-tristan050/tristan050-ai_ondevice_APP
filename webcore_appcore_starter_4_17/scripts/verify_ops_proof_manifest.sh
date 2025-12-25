#!/usr/bin/env bash
set -euo pipefail

# S6 Seal Manifest 검증 스크립트
# 금지: 로그/바디를 덤프하지 말 것(금지키 유출 위험). 파일명/경로 수준만 출력.

ROOT="$(git rev-parse --show-toplevel)/webcore_appcore_starter_4_17"
cd "$ROOT"

OPS_DIR="$ROOT/docs/ops"
MANIFEST="$OPS_DIR/r10-s6-seal-manifest.json"
CHECKSUMS="$OPS_DIR/r10-s6-seal-checksums.txt"

FAILURES=()

echo "[verify] S6 Seal Manifest Verification"

# 1) manifest 존재/JSON 파싱 가능
if [ ! -f "$MANIFEST" ]; then
  FAILURES+=("manifest file missing: $MANIFEST")
else
  if ! jq empty "$MANIFEST" 2>/dev/null; then
    FAILURES+=("manifest JSON parse failed: $MANIFEST")
  else
    echo "[OK] manifest exists and valid JSON"
  fi
fi

# 2) manifest.opsProofSets[].latest 파일 존재
if [ -f "$MANIFEST" ]; then
  latest_files=$(jq -r '.opsProofSets[].latest' "$MANIFEST" 2>/dev/null || echo "")
  for latest in $latest_files; do
    latest_path="$OPS_DIR/$latest"
    if [ ! -f "$latest_path" ]; then
      FAILURES+=("latest file missing: $latest")
    else
      echo "[OK] latest file exists: $latest"
    fi
  done
fi

# 3) 각 latest가 참조하는 artifacts(json/log)가 실제 존재
if [ -f "$MANIFEST" ]; then
  proof_sets=$(jq -c '.opsProofSets[]' "$MANIFEST" 2>/dev/null || echo "")
  while IFS= read -r proof_set; do
    [ -z "$proof_set" ] && continue
    
    latest=$(echo "$proof_set" | jq -r '.latest')
    artifacts=$(echo "$proof_set" | jq -r '.artifacts[]' 2>/dev/null || echo "")
    
    for artifact in $artifacts; do
      artifact_path="$OPS_DIR/$artifact"
      if [ ! -f "$artifact_path" ]; then
        FAILURES+=("artifact missing: $latest -> $artifact")
      else
        echo "[OK] artifact exists: $latest -> $artifact"
      fi
    done
  done <<< "$proof_sets"
fi

# 4) checksums 파일 존재 + 대상 파일들이 모두 checksums에 포함
if [ ! -f "$CHECKSUMS" ]; then
  FAILURES+=("checksums file missing: $CHECKSUMS")
else
  echo "[OK] checksums file exists"
  
  # manifest에 있는 모든 파일이 checksums에 포함되는지 확인
  if [ -f "$MANIFEST" ]; then
    # manifest + checksums 자신 + .latest + artifacts
    expected_files=(
      "$(basename "$MANIFEST")"
      "$(basename "$CHECKSUMS")"
    )
    
    latest_files=$(jq -r '.opsProofSets[].latest' "$MANIFEST" 2>/dev/null || echo "")
    for latest in $latest_files; do
      expected_files+=("$latest")
      
      # latest 파일에서 artifact 추출
      latest_path="$OPS_DIR/$latest"
      if [ -f "$latest_path" ]; then
        while IFS= read -r line || [ -n "$line" ]; do
          line=$(echo "$line" | sed 's/^[[:space:]]*//;s/[[:space:]]*$//')
          [ -z "$line" ] && continue
          
          if [[ "$line" =~ ^[a-zA-Z_]+= ]]; then
            value="${line#*=}"
            expected_files+=("$value")
          elif [[ "$line" =~ / ]]; then
            basename_file="$(basename "$line")"
            expected_files+=("$basename_file")
          else
            expected_files+=("$line")
          fi
        done < "$latest_path"
      fi
    done
    
    # checksums에 있는 파일명 추출 (정렬)
    checksum_files=$(grep -v '^#' "$CHECKSUMS" | awk '{print $2}' | sort)
    
    for expected in "${expected_files[@]}"; do
      if ! echo "$checksum_files" | grep -q "^${expected}$"; then
        FAILURES+=("file not in checksums: $expected")
      fi
    done
    
    echo "[OK] all expected files present in checksums"
  fi
fi

# 결과 출력
if [ ${#FAILURES[@]} -eq 0 ]; then
  echo "[PASS] S6 Seal Manifest Verification"
  exit 0
else
  echo "[FAIL] S6 Seal Manifest Verification"
  for failure in "${FAILURES[@]}"; do
    echo "  - $failure"
  done
  exit 1
fi

