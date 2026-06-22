#!/usr/bin/env bash
#
# build_runtime.sh — Butler 자립(self-contained) 앱용 번들 런타임 빌더 (macOS arm64)
#
# 이 스크립트가 만드는 것:
#   [1] 독립 파이썬 런타임  : src-tauri/python-runtime/bin/python3  (astral python-build-standalone)
#   [1] 가벼운 서빙 라이브러리: requirements-serving.txt 설치 (단, llama-cpp-python 은 제외 — [2]에서)
#   [3] 내장 4B 모델         : src-tauri/models/qwen3-4b-q4_k_m.gguf 복사
#
# 추론엔진(llama-cpp-python, Metal)은 무거운 컴파일이라 별도 단계 [2]로 분리한다:
#   CMAKE_ARGS="-DGGML_METAL=ON" \
#     butler-desktop/src-tauri/python-runtime/bin/python3 -m pip install llama-cpp-python
#
# 산출물(python-runtime/, models/)은 .gitignore 처리되어 커밋되지 않는다.
#
set -euo pipefail

# ── 경로 ───────────────────────────────────────────────────────
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SRC_TAURI="${REPO_ROOT}/butler-desktop/src-tauri"
RUNTIME_DIR="${SRC_TAURI}/python-runtime"
MODELS_DIR="${SRC_TAURI}/models"
REQUIREMENTS="${REPO_ROOT}/requirements-serving.txt"
MODEL_SRC="${HOME}/Desktop/butler-data/엔진모델/4B_엔진_gguf/qwen3-4b-q4_k_m.gguf"
MODEL_NAME="qwen3-4b-q4_k_m.gguf"

# ── python-build-standalone (macOS arm64, install_only) ───────
# 핀 고정으로 재현 가능하게 한다. 업데이트 시 TAG/PY_VER 두 줄만 교체.
PBS_TAG="20260610"
PY_VER="3.11.15"
PBS_ASSET="cpython-${PY_VER}+${PBS_TAG}-aarch64-apple-darwin-install_only.tar.gz"
PBS_URL="https://github.com/astral-sh/python-build-standalone/releases/download/${PBS_TAG}/${PBS_ASSET}"

PYBIN="${RUNTIME_DIR}/bin/python3"

log() { echo "[build_runtime] $*"; }

# ── [1a] 독립 파이썬 다운로드/배치 ────────────────────────────
if [[ -x "${PYBIN}" && "${1:-}" != "--force" ]]; then
  log "python-runtime 이미 존재: ${PYBIN} (다시 받으려면 --force)"
else
  log "독립 파이썬 다운로드: ${PBS_ASSET}"
  rm -rf "${RUNTIME_DIR}"
  mkdir -p "${RUNTIME_DIR}"
  TMP_TGZ="$(mktemp -t pbs).tar.gz"
  curl -fSL --retry 3 -o "${TMP_TGZ}" "${PBS_URL}"
  # install_only 아카이브의 최상위 디렉터리는 'python/' → strip 해서 bin/python3 가 바로 나오게
  tar -xzf "${TMP_TGZ}" -C "${RUNTIME_DIR}" --strip-components=1
  rm -f "${TMP_TGZ}"
  log "배치 완료: ${PYBIN}"
fi

if [[ ! -x "${PYBIN}" ]]; then
  log "ERROR: ${PYBIN} 가 실행 가능하지 않습니다. 배치 실패."
  exit 1
fi
log "파이썬 버전: $(${PYBIN} -V 2>&1)"

# ── [1b] 가벼운 서빙 라이브러리 설치 (llama-cpp-python 제외) ──
log "pip 업그레이드"
"${PYBIN}" -m pip install --upgrade pip >/dev/null

# requirements-serving.txt 에서 주석과 llama-cpp-python 라인을 제외한 임시 목록 생성.
FILTERED_REQ="$(mktemp -t reqs).txt"
grep -vE '^[[:space:]]*#' "${REQUIREMENTS}" | grep -viE 'llama-cpp-python' | grep -vE '^[[:space:]]*$' > "${FILTERED_REQ}"
log "설치할 서빙 라이브러리:"
sed 's/^/[build_runtime]   /' "${FILTERED_REQ}"
"${PYBIN}" -m pip install -r "${FILTERED_REQ}"
rm -f "${FILTERED_REQ}"
log "서빙 라이브러리 설치 완료 (llama-cpp-python 은 단계 [2]에서)"

# ── [3] 4B 모델 내장 복사 ─────────────────────────────────────
mkdir -p "${MODELS_DIR}"
if [[ -f "${MODELS_DIR}/${MODEL_NAME}" ]]; then
  log "모델 이미 존재: ${MODELS_DIR}/${MODEL_NAME}"
elif [[ -f "${MODEL_SRC}" ]]; then
  log "4B 모델 복사 중(~3.5GB)… ${MODEL_SRC}"
  cp "${MODEL_SRC}" "${MODELS_DIR}/${MODEL_NAME}"
  log "모델 복사 완료: ${MODELS_DIR}/${MODEL_NAME}"
else
  log "WARN: 원본 모델을 찾지 못함: ${MODEL_SRC} (단계 [3] 모델 복사는 건너뜀)"
fi

log "완료. 다음 단계:"
log "  [2] CMAKE_ARGS=\"-DGGML_METAL=ON\" ${PYBIN} -m pip install llama-cpp-python"
