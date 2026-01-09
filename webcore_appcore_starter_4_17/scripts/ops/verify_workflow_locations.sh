#!/usr/bin/env bash
# GitHub Actions 워크플로 위치 검증 (Fail-Closed)
# 루트 .github/workflows/*.yml|yaml 만 허용
# 중첩된 */.github/workflows/* 가 존재하면 FAIL

set -euo pipefail

ROOT="$(git rev-parse --show-toplevel 2>/dev/null)" || {
  echo "FAIL: not a git repository" >&2
  exit 2
}

cd "${ROOT}"

# 루트 워크플로 디렉터리
ROOT_WORKFLOWS_DIR=".github/workflows"

# 루트 워크플로 디렉터리 존재 확인
if [ ! -d "${ROOT_WORKFLOWS_DIR}" ]; then
  echo "FAIL: root workflows directory not found: ${ROOT_WORKFLOWS_DIR}" >&2
  exit 1
fi

# 중첩된 워크플로 검색 (node_modules 제외)
# find로 모든 .github/workflows 디렉터리를 찾되, 루트와 node_modules는 제외
NESTED_WORKFLOWS=$(find . -type d -path "*/.github/workflows" \
  ! -path "./.github/workflows" \
  ! -path "*/node_modules/*" \
  ! -path "./node_modules/*" \
  2>/dev/null | sort)

if [ -n "${NESTED_WORKFLOWS}" ]; then
  echo "FAIL: nested workflows directories found (only root .github/workflows allowed)" >&2
  echo "reason_code=NESTED_WORKFLOWS_DIRECTORY_FOUND" >&2
  echo "nested_directories:" >&2
  echo "${NESTED_WORKFLOWS}" | while IFS= read -r dir; do
    echo "  - ${dir}" >&2
  done
  
  # 중첩된 디렉터리의 워크플로 파일 목록 (경로만, meta-only)
  echo "nested_workflow_files:" >&2
  echo "${NESTED_WORKFLOWS}" | while IFS= read -r dir; do
    if [ -d "${dir}" ]; then
      find "${dir}" -type f \( -name "*.yml" -o -name "*.yaml" \) 2>/dev/null | while IFS= read -r file; do
        echo "  - ${file}" >&2
      done
    fi
  done
  
  exit 1
fi

# 중첩된 워크플로 파일 직접 검색 (디렉터리 검색이 실패한 경우 대비)
NESTED_FILES=$(find . -type f \( -name "*.yml" -o -name "*.yaml" \) \
  -path "*/.github/workflows/*" \
  ! -path "./.github/workflows/*" \
  ! -path "*/node_modules/*" \
  ! -path "./node_modules/*" \
  2>/dev/null | sort)

if [ -n "${NESTED_FILES}" ]; then
  echo "FAIL: nested workflow files found (only root .github/workflows allowed)" >&2
  echo "reason_code=NESTED_WORKFLOW_FILES_FOUND" >&2
  echo "nested_files:" >&2
  echo "${NESTED_FILES}" | while IFS= read -r file; do
    echo "  - ${file}" >&2
  done
  exit 1
fi

# PASS
echo "PASS: all workflows are in root .github/workflows"
echo "root_workflows_dir=${ROOT_WORKFLOWS_DIR}"
exit 0

