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

# ── 옵션 ───────────────────────────────────────────────────────
FORCE=0
MODEL_ONLY=0
for arg in "$@"; do
  case "${arg}" in
    --force)
      FORCE=1
      ;;
    --model-only)
      MODEL_ONLY=1
      ;;
    *)
      echo "[build_runtime] ERROR: 알 수 없는 옵션: ${arg}" >&2
      echo "[build_runtime] 사용법: scripts/build_runtime.sh [--force] [--model-only]" >&2
      exit 2
      ;;
  esac
done

is_truthy() {
  case "${1:-}" in
    1|true|TRUE|yes|YES|on|ON)
      return 0
      ;;
    *)
      return 1
      ;;
  esac
}

# ── 경로 ───────────────────────────────────────────────────────
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SRC_TAURI="${BUTLER_SRC_TAURI_DIR:-${REPO_ROOT}/butler-desktop/src-tauri}"
RUNTIME_DIR="${BUTLER_BUNDLE_RUNTIME_DIR:-${SRC_TAURI}/python-runtime}"
MODELS_DIR="${BUTLER_BUNDLE_MODELS_DIR:-${SRC_TAURI}/models}"
REQUIREMENTS="${REPO_ROOT}/requirements-serving.txt"
MODEL_SRC="${BUTLER_BUNDLE_MODEL_SRC:-${HOME}/Desktop/butler-data/엔진모델/4B_엔진_gguf/qwen3-4b-q4_k_m.gguf}"
MODEL_NAME="qwen3-4b-q4_k_m.gguf"
MODEL_DEST="${MODELS_DIR}/${MODEL_NAME}"

# ── python-build-standalone (macOS arm64, install_only) ───────
# 핀 고정으로 재현 가능하게 한다. 업데이트 시 TAG/PY_VER 두 줄만 교체.
PBS_TAG="20260610"
PY_VER="3.11.15"
PBS_ASSET="cpython-${PY_VER}+${PBS_TAG}-aarch64-apple-darwin-install_only.tar.gz"
PBS_URL="https://github.com/astral-sh/python-build-standalone/releases/download/${PBS_TAG}/${PBS_ASSET}"

PYBIN="${RUNTIME_DIR}/bin/python3"

log() { echo "[build_runtime] $*"; }

# Tauri bundle.resources 의 source 경로는 "없으면 건너뛰기"가 아니라 빌드 오류가 난다.
# self-contained 빌드는 모델 원본이 없으면 반드시 실패시켜 no_model/stub 번들을 막는다.
if [[ ! -f "${MODEL_DEST}" && ! -f "${MODEL_SRC}" ]] && ! is_truthy "${BUTLER_ALLOW_MISSING_BUNDLE_MODEL:-0}"; then
  log "ERROR: 원본 모델을 찾지 못함: ${MODEL_SRC}"
  log "ERROR: self-contained 앱 빌드에는 ${MODEL_NAME} 이 필요합니다."
  log "ERROR: 다른 위치를 쓰려면 BUTLER_BUNDLE_MODEL_SRC=/path/to/${MODEL_NAME} 를 지정하세요."
  log "ERROR: 의도적으로 모델 없는 리소스 디렉터리만 만들려면 BUTLER_ALLOW_MISSING_BUNDLE_MODEL=1 을 명시하세요."
  exit 1
fi

# ── [1a] 독립 파이썬 다운로드/배치 ────────────────────────────
if [[ "${MODEL_ONLY}" == "1" ]]; then
  log "model-only 모드: python-runtime 생성과 pip 설치는 건너뜁니다."
elif [[ -x "${PYBIN}" && "${FORCE}" != "1" ]]; then
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

if [[ "${MODEL_ONLY}" != "1" ]]; then
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
  "${PYBIN}" - <<'PY'
from jinja2.sandbox import SandboxedEnvironment
print("JINJA2_SANDBOX_IMPORT_OK=1")
PY
  rm -f "${FILTERED_REQ}"
  log "서빙 라이브러리 설치 완료 (llama-cpp-python 은 단계 [2]에서)"
fi

# ── [3] 4B 모델 내장 복사 ─────────────────────────────────────
mkdir -p "${MODELS_DIR}"
if [[ -f "${MODEL_DEST}" ]]; then
  log "모델 이미 존재: ${MODEL_DEST}"
elif [[ -f "${MODEL_SRC}" ]]; then
  log "4B 모델 복사 중(~3.5GB)… ${MODEL_SRC}"
  cp "${MODEL_SRC}" "${MODEL_DEST}"
  log "모델 복사 완료: ${MODEL_DEST}"
elif is_truthy "${BUTLER_ALLOW_MISSING_BUNDLE_MODEL:-0}"; then
  log "WARN: BUTLER_ALLOW_MISSING_BUNDLE_MODEL=1 이므로 모델 복사를 명시적으로 건너뜁니다."
else
  log "ERROR: 원본 모델을 찾지 못함: ${MODEL_SRC}"
  exit 1
fi

if [[ "${MODEL_ONLY}" == "1" ]]; then
  log "model-only 완료."
else
  log "완료. 다음 단계:"
  log "  [2] CMAKE_ARGS=\"-DGGML_METAL=ON\" ${PYBIN} -m pip install llama-cpp-python"
fi
