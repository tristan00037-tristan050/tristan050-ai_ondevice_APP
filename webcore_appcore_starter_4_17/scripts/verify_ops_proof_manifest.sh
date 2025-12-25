#!/usr/bin/env bash
set -euo pipefail

# S6 Seal Manifest 검증 스크립트
# 금지: 로그/바디를 덤프하지 말 것(금지키 유출 위험). 파일명/경로 수준만 출력.

ROOT="$(git rev-parse --show-toplevel)/webcore_appcore_starter_4_17"
cd "$ROOT"

OPS_DIR="$ROOT/docs/ops"
MANIFEST="$OPS_DIR/r10-s6-seal-manifest.json"
CHECKSUMS="$OPS_DIR/r10-s6-seal-checksums.txt"
CHECKSUMS_SHA="$OPS_DIR/r10-s6-seal-checksums.txt.sha256"

FAILURES=()

echo "[verify] S6 Seal Manifest Verification"

# 1) manifest 존재/JSON 파싱 가능/manifestVersion==1 확인
if [ ! -f "$MANIFEST" ]; then
  FAILURES+=("manifest file missing: $MANIFEST")
else
  if ! jq empty "$MANIFEST" 2>/dev/null; then
    FAILURES+=("manifest JSON parse failed: $MANIFEST")
  else
    echo "[OK] manifest exists and valid JSON"
    
    # manifestVersion==1 확인
    manifest_version=$(jq -r '.manifestVersion // empty' "$MANIFEST" 2>/dev/null)
    if [ "$manifest_version" != "1" ]; then
      FAILURES+=("manifestVersion must be 1, got: $manifest_version")
    else
      echo "[OK] manifestVersion == 1"
    fi
  fi
fi

# 2) fileCount == Object.keys(opsProofSets).length 확인
if [ -f "$MANIFEST" ]; then
  declared_file_count=$(jq -r '.fileCount' "$MANIFEST" 2>/dev/null || echo "")
  actual_proof_sets_count=$(jq '.opsProofSets | length' "$MANIFEST" 2>/dev/null || echo "")
  
    if [ "$declared_file_count" != "$actual_proof_sets_count" ]; then
      FAILURES+=("fileCount mismatch: declared=$declared_file_count, actual opsProofSets.length=$actual_proof_sets_count")
    else
      echo "[OK] fileCount == opsProofSets.length ($actual_proof_sets_count)"
    fi
fi

# 3) manifest.opsProofSets[].latest 파일 존재
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

# 4) 각 latest가 참조하는 artifacts(json/log)가 실제 존재
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

# 5) checksums 파일 존재 + 커버리지 100% + 혼입 방지
if [ ! -f "$CHECKSUMS" ]; then
  FAILURES+=("checksums file missing: $CHECKSUMS")
else
  echo "[OK] checksums file exists"
  
  if [ -f "$MANIFEST" ]; then
    # manifest가 참조하는 모든 파일 수집 (manifest + .latest + artifacts)
    # checksums 자신은 포함하지 않음
    expected_files=(
      "$(basename "$MANIFEST")"
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
    expected_files_sorted=$(printf '%s\n' "${expected_files[@]}" | sort -u)
    
    # 커버리지 100% 확인: 모든 expected 파일이 checksums에 포함되어야 함
    for expected in $expected_files_sorted; do
      if ! echo "$checksum_files" | grep -q "^${expected}$"; then
        FAILURES+=("file not in checksums (coverage gap): $expected")
      fi
    done
    
    # 혼입 방지: checksums에 manifest가 참조하지 않는 파일이 있으면 FAIL
    for checksum_file in $checksum_files; do
      if ! echo "$expected_files_sorted" | grep -q "^${checksum_file}$"; then
        FAILURES+=("file in checksums but not referenced by manifest (contamination): $checksum_file")
      fi
    done
    
    if [ ${#FAILURES[@]} -eq 0 ]; then
      echo "[OK] checksums coverage 100% (no gaps, no contamination)"
    fi
  fi
fi

# 6) checksums.txt.sha256로 checksums.txt 무결성 확인
if [ ! -f "$CHECKSUMS_SHA" ]; then
  FAILURES+=("checksums SHA256 file missing: $CHECKSUMS_SHA")
else
  echo "[OK] checksums SHA256 file exists"
  
  if [ -f "$CHECKSUMS" ]; then
    # checksums.txt의 실제 SHA256 계산
    if command -v shasum >/dev/null 2>&1; then
      actual_sha=$(shasum -a 256 "$CHECKSUMS" | cut -d' ' -f1)
    elif command -v sha256sum >/dev/null 2>&1; then
      actual_sha=$(sha256sum "$CHECKSUMS" | cut -d' ' -f1)
    else
      FAILURES+=("no sha256 command found for integrity check")
    fi
    
    # checksums.txt.sha256에서 저장된 SHA256 읽기
    stored_sha=$(awk '{print $1}' "$CHECKSUMS_SHA" 2>/dev/null | head -1)
    
    if [ "$actual_sha" != "$stored_sha" ]; then
      FAILURES+=("checksums.txt integrity mismatch: actual=$actual_sha, stored=$stored_sha")
    else
      echo "[OK] checksums.txt integrity verified"
    fi
  fi
fi

# 7) 금지키 스캔 (본문 덤프 없이)
# JSON 키로 사용되는 금지키만 감지 (예: "prompt":, "text":)
if [ -f "$MANIFEST" ]; then
  # JSON 키 패턴 (따옴표로 감싸진 키만 감지)
  BANNED_KEY_PATTERNS='"(prompt|text|body|context|snippet|excerpt|ticket|document|message|content|ragText|ragChunk|ragContext|ragQuery|ragResult|ragSource|errorMessage|errorText|suggestionText|responseText)"\s*:'
  
  proof_sets=$(jq -c '.opsProofSets[]' "$MANIFEST" 2>/dev/null || echo "")
  while IFS= read -r proof_set; do
    [ -z "$proof_set" ] && continue
    
    artifacts=$(echo "$proof_set" | jq -r '.artifacts[]' 2>/dev/null || echo "")
    for artifact in $artifacts; do
      artifact_path="$OPS_DIR/$artifact"
      if [ -f "$artifact_path" ]; then
        # JSON 파일인 경우에만 키 패턴 체크
        if [[ "$artifact" =~ \.json$ ]]; then
          if command -v rg >/dev/null 2>&1; then
            if rg -qi "$BANNED_KEY_PATTERNS" "$artifact_path" 2>/dev/null; then
              FAILURES+=("banned JSON key detected in artifact: $artifact")
            fi
          elif command -v grep >/dev/null 2>&1; then
            if grep -qiE "$BANNED_KEY_PATTERNS" "$artifact_path" 2>/dev/null; then
              FAILURES+=("banned JSON key detected in artifact: $artifact")
            fi
          fi
        fi
        # 로그 파일은 일반 텍스트가 포함될 수 있으므로 스캔 제외
        # (로그는 게이트 실행 결과이므로 금지키가 아닌 일반 메시지일 수 있음)
      fi
    done
  done <<< "$proof_sets"
  
  if [ ${#FAILURES[@]} -eq 0 ]; then
    echo "[OK] banned key scan passed (no JSON keys detected)"
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

