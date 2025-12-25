#!/usr/bin/env bash
set -euo pipefail

# S6 봉인 manifest/checksums 생성 스크립트
# 주의: 기존 proof를 새로 만들지 않고, manifest/checksums만 생성

ROOT="$(git rev-parse --show-toplevel)/webcore_appcore_starter_4_17"
cd "$ROOT"

OPS_DIR="$ROOT/docs/ops"
MANIFEST="$OPS_DIR/r10-s6-seal-manifest.json"
CHECKSUMS="$OPS_DIR/r10-s6-seal-checksums.txt"

VERIFIED_COMMIT="$(git rev-parse --short HEAD)"
SEALED_AT="$(date -u +"%Y-%m-%dT%H:%M:%SZ")"

echo "[generate] Creating S6 seal manifest and checksums..."

# S6 봉인에 포함된 .latest 파일 목록 (S6 관련)
S6_LATEST_FILES=(
  "r10-s6-4-perf-proof.latest"
  "r10-s5-p1-4-perf-kpi-proof.latest"
)

# .latest 파일에서 artifact 추출 함수
parse_latest_file() {
  local latest_file="$1"
  local artifacts=()
  
  if [ ! -f "$latest_file" ]; then
    return 1
  fi
  
  while IFS= read -r line || [ -n "$line" ]; do
    line=$(echo "$line" | sed 's/^[[:space:]]*//;s/[[:space:]]*$//')
    [ -z "$line" ] && continue
    
    # key=value 형식 (예: json=...)
    if [[ "$line" =~ ^[a-zA-Z_]+= ]]; then
      local value="${line#*=}"
      artifacts+=("$value")
    # 절대 경로인 경우 파일명만 추출
    elif [[ "$line" =~ / ]]; then
      local basename_file="$(basename "$line")"
      artifacts+=("$basename_file")
    # 단순 파일명
    else
      artifacts+=("$line")
    fi
  done < "$latest_file"
  
  printf '%s\n' "${artifacts[@]}"
}

# opsProofSets 배열 생성
ops_proof_sets=()
total_file_count=0

for latest_file in "${S6_LATEST_FILES[@]}"; do
  latest_path="$OPS_DIR/$latest_file"
  
  if [ ! -f "$latest_path" ]; then
    echo "[warn] $latest_file not found, skipping"
    continue
  fi
  
  artifacts=()
  while IFS= read -r artifact; do
    [ -z "$artifact" ] && continue
    artifact_path="$OPS_DIR/$artifact"
    if [ -f "$artifact_path" ]; then
      artifacts+=("$artifact")
      ((total_file_count++))
    fi
  done < <(parse_latest_file "$latest_path")
  
  if [ ${#artifacts[@]} -gt 0 ]; then
    artifacts_json=""
    for artifact in "${artifacts[@]}"; do
      if [ -z "$artifacts_json" ]; then
        artifacts_json="\"$artifact\""
      else
        artifacts_json="$artifacts_json, \"$artifact\""
      fi
    done
    
    ops_proof_sets+=("{\"latest\":\"$latest_file\",\"artifacts\":[$artifacts_json]}")
  fi
done

# manifest JSON 생성
proof_sets_json="$(IFS=,; echo "${ops_proof_sets[*]}")"

cat > "$MANIFEST" <<EOF
{
  "sealVersion": "1.0",
  "verifiedCommit": "$VERIFIED_COMMIT",
  "sealedAt": "$SEALED_AT",
  "fileCount": $total_file_count,
  "opsProofSets": [$proof_sets_json]
}
EOF

echo "[generate] Manifest created: $MANIFEST"

# checksums 생성
echo "[generate] Generating checksums..."

# 대상 파일 목록: manifest + checksums 자신 + .latest + artifacts
checksum_files=(
  "$(basename "$MANIFEST")"
  "$(basename "$CHECKSUMS")"
)

for latest_file in "${S6_LATEST_FILES[@]}"; do
  checksum_files+=("$latest_file")
  latest_path="$OPS_DIR/$latest_file"
  
  if [ -f "$latest_path" ]; then
    while IFS= read -r artifact; do
      [ -z "$artifact" ] && continue
      artifact_path="$OPS_DIR/$artifact"
      if [ -f "$artifact_path" ]; then
        checksum_files+=("$artifact")
      fi
    done < <(parse_latest_file "$latest_path")
  fi
done

# 파일명 정렬 후 checksums 생성
{
  echo "# S6 Seal Checksums (SHA256)"
  echo "# Generated: $SEALED_AT"
  echo "# Verified Commit: $VERIFIED_COMMIT"
  echo ""
  
  for file in $(printf '%s\n' "${checksum_files[@]}" | sort -u); do
    file_path="$OPS_DIR/$file"
    if [ -f "$file_path" ]; then
      if command -v shasum >/dev/null 2>&1; then
        checksum=$(shasum -a 256 "$file_path" | cut -d' ' -f1)
      elif command -v sha256sum >/dev/null 2>&1; then
        checksum=$(sha256sum "$file_path" | cut -d' ' -f1)
      else
        echo "[error] No sha256 command found"
        exit 1
      fi
      echo "$checksum  $file"
    fi
  done
} > "$CHECKSUMS"

echo "[generate] Checksums created: $CHECKSUMS"
echo "[generate] Total files: $total_file_count"
echo "[generate] Done."

