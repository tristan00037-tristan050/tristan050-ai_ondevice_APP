#!/usr/bin/env bash
set -euo pipefail

SOURCE_DIR="${SOURCE_DIR:-tmp/sample_data}"
OUTPUT_DIR="${OUTPUT_DIR:-tmp/sample_out}"
DRY_RUN="${DRY_RUN:-1}"

echo "========================================"
echo " Butler AI 데이터 파이프라인 실행"
echo " source_dir: ${SOURCE_DIR}"
echo " output_dir: ${OUTPUT_DIR}"
echo " dry_run:    ${DRY_RUN}"
echo "========================================"

if [[ ! -d "${SOURCE_DIR}" ]]; then
  echo "[오류] SOURCE_DIR가 존재하지 않습니다: ${SOURCE_DIR}" >&2
  exit 1
fi

cmd=(python scripts/pipeline/pipeline_runner_v2.py --source-dir "${SOURCE_DIR}" --output-dir "${OUTPUT_DIR}")
if [[ "${DRY_RUN}" == "1" || "${DRY_RUN}" == "true" || "${DRY_RUN}" == "TRUE" ]]; then
  cmd+=(--dry-run)
fi

"${cmd[@]}"
