#!/usr/bin/env bash
set -euo pipefail

# S6 봉인 manifest/checksums 생성 스크립트
# 주의: 기존 proof를 새로 만들지 않고, manifest/checksums만 생성

ROOT="$(git rev-parse --show-toplevel)/webcore_appcore_starter_4_17"
cd "$ROOT"

OPS_DIR="$ROOT/docs/ops"
MANIFEST="$OPS_DIR/r10-s6-seal-manifest.json"
CHECKSUMS="$OPS_DIR/r10-s6-seal-checksums.txt"
CHECKSUMS_SHA="$OPS_DIR/r10-s6-seal-checksums.txt.sha256"

VERIFIED_COMMIT_FULL="$(git rev-parse HEAD)"
VERIFIED_COMMIT_SHORT="$(git rev-parse --short HEAD)"
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

# opsProofSets 배열 생성 (사전순 정렬 보장)
ops_proof_sets=()

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
    fi
  done < <(parse_latest_file "$latest_path")
  
  if [ ${#artifacts[@]} -gt 0 ]; then
    # artifacts 정렬 (결정성 보장)
    sorted_artifacts=$(printf '%s\n' "${artifacts[@]}" | sort)
    
    artifacts_json=""
    while IFS= read -r artifact; do
      [ -z "$artifact" ] && continue
      if [ -z "$artifacts_json" ]; then
        artifacts_json="\"$artifact\""
      else
        artifacts_json="$artifacts_json, \"$artifact\""
      fi
    done <<< "$sorted_artifacts"
    
    ops_proof_sets+=("{\"latest\":\"$latest_file\",\"artifacts\":[$artifacts_json]}")
  fi
done

# opsProofSets를 사전순 정렬 (결정성 보장)
# latest 파일명 기준으로 정렬
sorted_proof_sets=$(printf '%s\n' "${ops_proof_sets[@]}" | jq -s 'sort_by(.latest)')

# fileCount = Object.keys(opsProofSets).length (manifest 내부 정의와 일치)
file_count=$(echo "$sorted_proof_sets" | jq 'length')

# manifest JSON 생성 (jq로 정렬된 상태로 생성)
cat > "$MANIFEST" <<EOF
{
  "manifestVersion": 1,
  "fileCountDefinition": "fileCount = Object.keys(opsProofSets).length",
  "verifiedCommit": "$VERIFIED_COMMIT_FULL",
  "verifiedCommitShort": "$VERIFIED_COMMIT_SHORT",
  "sealedAt": "$SEALED_AT",
  "fileCount": $file_count,
  "opsProofSets": $(echo "$sorted_proof_sets" | jq -c '.')
}
EOF

echo "[generate] Manifest created: $MANIFEST"

# checksums 생성
echo "[generate] Generating checksums..."

# 대상 파일 목록: manifest + .latest + artifacts (checksums 자신은 제외)
checksum_files=(
  "$(basename "$MANIFEST")"
)

# manifest에서 참조하는 모든 .latest + artifacts 수집
for latest_file in "${S6_LATEST_FILES[@]}"; do
  latest_path="$OPS_DIR/$latest_file"
  
  if [ -f "$latest_path" ]; then
    checksum_files+=("$latest_file")
    while IFS= read -r artifact; do
      [ -z "$artifact" ] && continue
      artifact_path="$OPS_DIR/$artifact"
      if [ -f "$artifact_path" ]; then
        checksum_files+=("$artifact")
      fi
    done < <(parse_latest_file "$latest_path")
  fi
done

# 파일명 정렬 후 checksums 생성 (결정성 보장)
{
  echo "# S6 Seal Checksums (SHA256)"
  echo "# Generated: $SEALED_AT"
  echo "# Verified Commit: $VERIFIED_COMMIT_FULL"
  echo "# Note: This file's checksum is stored in r10-s6-seal-checksums.txt.sha256"
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

# checksums.txt.sha256 생성 (자기참조 제거)
if command -v shasum >/dev/null 2>&1; then
  checksums_sha=$(shasum -a 256 "$CHECKSUMS" | cut -d' ' -f1)
elif command -v sha256sum >/dev/null 2>&1; then
  checksums_sha=$(sha256sum "$CHECKSUMS" | cut -d' ' -f1)
else
  echo "[error] No sha256 command found"
  exit 1
fi

echo "$checksums_sha  $(basename "$CHECKSUMS")" > "$CHECKSUMS_SHA"

echo "[generate] Checksums created: $CHECKSUMS"
echo "[generate] Checksums SHA256 created: $CHECKSUMS_SHA"
echo "[generate] File count (opsProofSets.length): $file_count"
echo "[generate] Done."

