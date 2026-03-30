#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="${REPO_DIR:-$(cd "$SCRIPT_DIR/../.." && pwd)}"
ADAPTER_DIR="${ADAPTER_DIR:-output/butler_model_small_v1}"
WORK_DIR="${WORK_DIR:-output/convert_work}"
PACKAGE_DIR="${PACKAGE_DIR:-output/butler_mobile_package}"
VERSION="${VERSION:-butler_model_small_v1}"
DRY_RUN="${DRY_RUN:-false}"
VENV_ACTIVATE="${VENV_ACTIVATE:-/root/butler-venv/bin/activate}"

cd "$REPO_DIR"

if [ -f "$VENV_ACTIVATE" ]; then
    # shellcheck disable=SC1090
    source "$VENV_ACTIVATE"
fi

if [ "$DRY_RUN" = "true" ]; then
    python scripts/convert/convert_runner_v2.py \
        --adapter-dir "$ADAPTER_DIR" \
        --work-dir "$WORK_DIR" \
        --package-dir "$PACKAGE_DIR" \
        --version "$VERSION" \
        --dry-run
else
    python scripts/convert/convert_runner_v2.py \
        --adapter-dir "$ADAPTER_DIR" \
        --work-dir "$WORK_DIR" \
        --package-dir "$PACKAGE_DIR" \
        --version "$VERSION"
fi
