#!/bin/bash
# Butler 완성품 빌드 — 한 번에 조립되는 완전한 앱
# 부품을 매번 급조하지 않도록, 빌드+llama-cpp+모델확인+검증을 1개 스크립트로.
set -uo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT/butler-desktop/src-tauri"
APP="target/release/bundle/macos/Butler.app"
RES="$APP/Contents/Resources"
PRODUCTION_A4_AUTHORITY="${BUTLER_A4_PRODUCTION_AUTHORITY_BUILD:-0}"
AUTHORITY_HELPER_EXE="$APP/Contents/XPCServices/A4VerifierAuthority.xpc/Contents/MacOS/A4VerifierAuthority"
PRODUCTION_BOX5_AUTHORITY="${BUTLER_BOX5_PRODUCTION_AUTHORITY_BUILD:-0}"
BOX5_AUTHORITY_HELPER="$RES/box5/Box5UserAuthority"
BOX5_AUTHORITY_POLICY="$RES/box5/authorization-trust-policy-v2.json"
RELEASE_DISTRIBUTION="${BUTLER_RELEASE_DISTRIBUTION-0}"
case "$RELEASE_DISTRIBUTION" in
  0|1) ;;
  *)
    echo "❌ RELEASE_DISTRIBUTION_FLAG_INVALID — BUTLER_RELEASE_DISTRIBUTION은 0 또는 1만 허용"
    exit 1
    ;;
esac
case "$PRODUCTION_BOX5_AUTHORITY" in
  0|1) ;;
  *)
    echo "❌ BOX5_AUTHORITY_BUILD_FLAG_INVALID — BUTLER_BOX5_PRODUCTION_AUTHORITY_BUILD는 0 또는 1만 허용"
    exit 1
    ;;
esac
if [[ "$RELEASE_DISTRIBUTION" == "1" && "$PRODUCTION_BOX5_AUTHORITY" != "1" ]]; then
  echo "❌ BLOCK_APPROVED_PRODUCTION_TRUST_POLICY_UNAVAILABLE — 배포 앱은 Box5 승인 정책·native authority가 필요합니다."
  exit 1
fi
export BUTLER_RELEASE_DISTRIBUTION="$RELEASE_DISTRIBUTION"

echo "════════════════════════════════════════"
echo " Butler 완성품 빌드 시작"
echo "════════════════════════════════════════"

echo "[0/5] 생산 빌드 컨텍스트 준비 (BUILD_CONTEXT.json)"
# 72cfd151(첫 화면 개편) 이후 production 빌드는 web(vite.config.ts)과 native(src-tauri/build.rs)
# 양쪽에서 불변 build context 를 요구한다. 이 단계가 없으면 BUILD_CONTEXT_PATH_REQUIRED /
# BUILD_CONTEXT_DIGEST_REQUIRED 로 중단된다. 절차는 .github/workflows/firstscreen-v2-5.yml 과
# docs/product/firstscreen_v2_5/REPRODUCE.md 를 그대로 따른다.

# clean-tree 는 보안 계약이다(build_with_git.py, firstscreen-v2-5.yml). 느슨하게 만들지 않는다.
# 위반 시 무엇이 걸렸는지 그대로 보여 주고 중단한다. 자동 정리·무시목록 추가는 하지 않는다.
if [[ -n "$(cd "$ROOT" && git status --porcelain --untracked-files=all)" ]]; then
  echo "❌ CLEAN_TREE_VIOLATION — 아래 항목 때문에 중단한다(자동 정리하지 않음)"
  (cd "$ROOT" && git status --porcelain --untracked-files=all)
  exit 1
fi

# CI 는 python 3.12 로 계약 스크립트를 돌린다. 시스템 python3 가 더 낮은 경우가 있어 명시한다.
CONTEXT_PY="${BUTLER_BUILD_CONTEXT_PYTHON:-python3.12}"
command -v "$CONTEXT_PY" >/dev/null 2>&1 || {
  echo "❌ $CONTEXT_PY 없음 — BUTLER_BUILD_CONTEXT_PYTHON 으로 3.12 인터프리터를 지정하라"; exit 1;
}

if [[ -n "${BUTLER_BUILD_CONTEXT_PATH:-}" ]]; then
  echo "  ℹ️ 외부에서 전달된 BUILD_CONTEXT 사용: $BUTLER_BUILD_CONTEXT_PATH"
else
  # 임시 산출물은 저장소 밖에 둔다. 저장소 안에 쓰면 그 파일이 clean-tree 검사를 스스로 깬다.
  CONTEXT_DIR="$(mktemp -d)" || { echo "❌ 임시 디렉터리 생성 실패"; exit 1; }
  case "$CONTEXT_DIR" in
    "$ROOT"/*|"$ROOT") echo "❌ 임시 경로가 저장소 안이다: $CONTEXT_DIR"; exit 1;;
  esac

  CONTEXT_BASELINE="${BUTLER_BUILD_CONTEXT_BASELINE:-HEAD^}"
  CONTEXT_HEAD="$(cd "$ROOT" && git rev-parse --verify 'HEAD^{commit}')" || {
    echo "❌ HEAD commit 확인 실패"; exit 1;
  }
  CONTEXT_REPOSITORY="${BUTLER_BUILD_CONTEXT_REPOSITORY:-}"
  if [[ -z "$CONTEXT_REPOSITORY" ]]; then
    CONTEXT_REPOSITORY="$(cd "$ROOT" && git remote get-url origin 2>/dev/null \
      | sed -e 's#^git@[^:]*:##' -e 's#^https\{0,1\}://[^/]*/##' -e 's#\.git$##')"
  fi
  [[ "$CONTEXT_REPOSITORY" =~ ^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$ ]] || {
    echo "❌ repository 식별자 유도 실패 — BUTLER_BUILD_CONTEXT_REPOSITORY 로 지정하라"; exit 1;
  }

  # ★workflow identity: 로컬 빌드는 로컬 식별자를 쓴다. CI 워크플로 ref 를 쓰면
  #   "CI 가 돌았다"는 거짓 기재가 된다.
  CONTEXT_WORKFLOW="local/scripts/build_complete_app.sh@${CONTEXT_HEAD}"
  # ★toolchain identity: 이 기계의 실측값만 기록한다. CI 고정값을 복사하지 않는다.
  CONTEXT_TOOLCHAIN="python=$("$CONTEXT_PY" -c 'import platform;print(platform.python_version())');node=$(node --version | sed 's/^v//');rust=$(rustc --version | awk '{print $2}')"

  ( cd "$ROOT" && "$CONTEXT_PY" scripts/release/build_safe_source_archive.py \
      --commit HEAD --scope-baseline "$CONTEXT_BASELINE" \
      --output "$CONTEXT_DIR/source.zip" --manifest "$CONTEXT_DIR/SOURCE_ARCHIVE_MANIFEST.json" ) || {
    echo "❌ source archive 생성 실패"; exit 1;
  }
  ( cd "$ROOT" && "$CONTEXT_PY" scripts/release/build_with_git.py \
      --output "$CONTEXT_DIR/BUILD_CONTEXT.json" \
      --source-manifest "$CONTEXT_DIR/SOURCE_ARCHIVE_MANIFEST.json" \
      --repository "$CONTEXT_REPOSITORY" \
      --workflow-identity "$CONTEXT_WORKFLOW" \
      --toolchain-identity "$CONTEXT_TOOLCHAIN" \
      --baseline "$CONTEXT_BASELINE" ) || { echo "❌ BUILD_CONTEXT 생성 실패"; exit 1; }
  ( cd "$ROOT" && "$CONTEXT_PY" scripts/release/verify_source_bundle.py \
      --archive "$CONTEXT_DIR/source.zip" \
      --manifest "$CONTEXT_DIR/SOURCE_ARCHIVE_MANIFEST.json" \
      --build-context "$CONTEXT_DIR/BUILD_CONTEXT.json" \
      --extract-to "$CONTEXT_DIR/no-git" ) || { echo "❌ source bundle 결속 검증 실패"; exit 1; }

  export BUTLER_BUILD_CONTEXT_PATH="$CONTEXT_DIR/BUILD_CONTEXT.json"
  echo "  ✅ BUILD_CONTEXT 생성: $BUTLER_BUILD_CONTEXT_PATH"
fi

BUILD_CONTEXT_DIGEST="$( ( cd "$ROOT" && "$CONTEXT_PY" scripts/verify/verify_build_context.py "$BUTLER_BUILD_CONTEXT_PATH" ) \
  | "$CONTEXT_PY" -c 'import json,sys; print(json.load(sys.stdin)["digest"])')" || {
  echo "❌ BUILD_CONTEXT 검증 실패"; exit 1;
}
[[ "$BUILD_CONTEXT_DIGEST" =~ ^[0-9a-f]{64}$ ]] || { echo "❌ context digest 형식 위반"; exit 1; }

# native(build.rs)는 release 프로파일에서 아래 4개를 모두 요구한다.
export BUTLER_BUILD_CONTEXT_DIGEST="$BUILD_CONTEXT_DIGEST"
BUTLER_SOURCE_COMMIT_OID="$(cd "$ROOT" && git rev-parse --verify 'HEAD^{commit}')" || exit 1
BUTLER_SOURCE_TREE_OID="$(cd "$ROOT" && git rev-parse --verify 'HEAD^{tree}')" || exit 1
export BUTLER_SOURCE_COMMIT_OID BUTLER_SOURCE_TREE_OID

# ★root bootstrap anchor 는 owner root 키 세리머니의 산출물이다(첫 화면 범위확정 문서 §3 IM-10,
#   배포 개시 전 이월 항목). 저장소에 정본이 없으므로 임의 생성은 금지한다 — 거짓 신뢰근거가 된다.
#   배포 빌드(BUTLER_RELEASE_DISTRIBUTION=1)에서는 반드시 있어야 하고, 내부 빌드에서는
#   없는 채로 진행하되 그 사실을 BUILD_INFO 에 남긴다.
BUILD_INFO_DISTRIBUTION_ARGS=()
if [[ "$RELEASE_DISTRIBUTION" == "1" ]]; then
  if [[ -z "${BUTLER_FIRSTSCREEN_ROOT_ANCHOR_SHA256:-}" ]]; then
    echo "❌ FIRSTSCREEN_ROOT_ANCHOR_REQUIRED — 배포 빌드는 부트스트랩 root anchor 를 요구한다."
    echo "   값의 정의: 앱이 최초 신뢰 부트스트랩에서 받아들일 root-policy 문서의 canonical digest"
    echo "   (butler-desktop/src-tauri/src/runtime_trust/verifier.rs 의 BLOCK_ROOT_BOOTSTRAP_ANCHOR)."
    echo "   ★임의 값 생성 금지. 세리머니로 확정된 값을"
    echo "   BUTLER_FIRSTSCREEN_ROOT_ANCHOR_SHA256=<64자리 소문자 hex> 로 전달하라."
    exit 1
  fi
  [[ "${BUTLER_FIRSTSCREEN_ROOT_ANCHOR_SHA256}" =~ ^[0-9a-f]{64}$ ]] || {
    echo "❌ root anchor 형식 위반(64자리 소문자 hex 아님)"; exit 1;
  }
  export BUTLER_FIRSTSCREEN_ROOT_ANCHOR_SHA256
  BUILD_INFO_DISTRIBUTION_ARGS=(--release-distribution --root-anchor "$BUTLER_FIRSTSCREEN_ROOT_ANCHOR_SHA256")
  echo "  ✅ 배포 빌드 — root anchor 결속"
else
  if [[ -n "${BUTLER_FIRSTSCREEN_ROOT_ANCHOR_SHA256:-}" ]]; then
    [[ "${BUTLER_FIRSTSCREEN_ROOT_ANCHOR_SHA256}" =~ ^[0-9a-f]{64}$ ]] || {
      echo "❌ root anchor 형식 위반(64자리 소문자 hex 아님)"; exit 1;
    }
    export BUTLER_FIRSTSCREEN_ROOT_ANCHOR_SHA256
    BUILD_INFO_DISTRIBUTION_ARGS=(--root-anchor "$BUTLER_FIRSTSCREEN_ROOT_ANCHOR_SHA256")
  fi
  echo "  ℹ️ 내부 빌드(BUTLER_RELEASE_DISTRIBUTION=0) — ★배포용 아님으로 BUILD_INFO 에 표시한다."
  echo "     root anchor 미결속 상태이므로 최초 신뢰 부트스트랩은 차단된다(설계대로)."
fi
echo "  ✅ build context digest $BUILD_CONTEXT_DIGEST · source $BUTLER_SOURCE_COMMIT_OID"

echo "[0.5/5] Box2 adapter 검증·번들 리소스 배치"
BOX2_ADAPTER_SRC="${BUTLER_BOX2_ADAPTER_SRC:-$HOME/Desktop/butler-data/정리8박스모음/Butler빌드자산통합/box2_adapter}"
BOX2_ADAPTER_DST="$ROOT/butler-desktop/src-tauri/models/box2/box2_adapter"
BOX2_REWRITE_WEIGHT_SHA256="92e8454fdc01d9bb002a510b2fdaecabcc9b9cbf964b6e48e5d61c23b5ace4b0"
if ! "$CONTEXT_PY" "$ROOT/scripts/stage_box2_adapter.py" \
  --source "$BOX2_ADAPTER_SRC" \
  --destination "$BOX2_ADAPTER_DST" \
  --expected-weight-sha256 "$BOX2_REWRITE_WEIGHT_SHA256"; then
  echo "❌ BOX2_ADAPTER_STAGE_FAILED — Box2 adapter 없는 앱 빌드 차단"
  exit 1
fi

echo "[1/5] Tauri 빌드 (.app)"
# pipefail(4행)로 npm 실패는 파이프 종료코드에 반영된다. 과거 `|| true` 가 이를 가려
# beforeBuildCommand(build_runtime.sh) 실패 시 STALE 번들을 성공으로 오인했다 — 제거한다.
( cd "$ROOT/butler-desktop" && npm run tauri build 2>&1 | tail -30 )
TAURI_RC=$?
[[ $TAURI_RC -eq 0 ]] || { echo "❌ tauri build 실패 (exit $TAURI_RC) — STALE 번들 방지 위해 중단"; exit 1; }
[[ -d "$APP" ]] || { echo "❌ .app 생성 실패"; exit 1; }
echo "  ✅ .app 생성"

# CI(firstscreen-v2-5.yml)와 같은 확인: 생산 바이트에 context digest 가 실제로 각인됐는가.
grep -R --fixed-strings "$BUILD_CONTEXT_DIGEST" "$ROOT/butler-desktop/dist" >/dev/null || {
  echo "❌ 생산 바이트에 build context digest 미각인 — 결속 없는 앱 생성 차단"; exit 1;
}
echo "  ✅ dist 에 context digest 각인 확인"

echo "[2/5] llama-cpp 설치 (자립 앱의 필수 부품)"
APP_PY="$RES/python/bin/python3"
if ! "$APP_PY" -c "import llama_cpp" 2>/dev/null; then
  CMAKE_ARGS="-DGGML_METAL=ON" "$APP_PY" -m pip install llama-cpp-python 2>&1 | tail -2
fi
"$APP_PY" -c "import llama_cpp; print('  ✅ llama-cpp', llama_cpp.__version__)" || { echo "❌ llama-cpp 실패"; exit 1; }

echo "[3/5] 모델 파일 확인 (4B 자유대화 + 1.7B 박스3)"
M4="$RES/models/qwen3-4b-q4_k_m.gguf"
M17="$RES/models/box3/butler-1.7b-v9-2-r2b-q4_k_m.gguf"
[[ -f "$M4" ]] && echo "  ✅ 4B: $(du -h "$M4" | cut -f1)" || { echo "❌ 4B 없음"; exit 1; }
[[ -f "$M17" ]] && echo "  ✅ 1.7B: $(du -h "$M17" | cut -f1)" || { echo "❌ 1.7B 없음"; exit 1; }

echo "[3.5/5] 회계 adapter 배치 (박스5 4B 회계)"
ACC_SRC="${ACCOUNTING_PEFT_ADAPTER_PATH:-}"
ACC_DST="$RES/butler_pc_core/accounting/models/qwen3_4b_accounting_v1"
if [[ -n "$ACC_SRC" ]]; then
  [[ -d "$ACC_SRC" && ! -L "$ACC_SRC" ]] || {
    echo "❌ 회계 adapter 경로가 유효한 디렉터리가 아님"; exit 1;
  }
  [[ -f "$ACC_SRC/adapter_config.json" && ! -L "$ACC_SRC/adapter_config.json" ]] || {
    echo "❌ 회계 adapter_config.json 누락/링크 거부"; exit 1;
  }
  [[ -s "$ACC_SRC/adapter_model.safetensors" && ! -L "$ACC_SRC/adapter_model.safetensors" ]] || {
    echo "❌ 회계 adapter_model.safetensors 누락/빈 파일/링크 거부"; exit 1;
  }
  "$APP_PY" -c 'import json,sys; c=json.load(open(sys.argv[1], encoding="utf-8")); assert isinstance(c,dict) and c.get("base_model_name_or_path")=="Qwen/Qwen3-4B"' "$ACC_SRC/adapter_config.json" || {
    echo "❌ 회계 adapter base model 계약 불일치"; exit 1;
  }
  rm -rf "$ACC_DST" || { echo "❌ 기존 회계 adapter 정리 실패"; exit 1; }
  mkdir -p "$(dirname "$ACC_DST")" || { echo "❌ 회계 adapter 대상 생성 실패"; exit 1; }
  cp -R "$ACC_SRC" "$ACC_DST" || { echo "❌ 회계 adapter 복사 실패"; exit 1; }
  echo "  ✅ 검증된 회계 adapter를 앱 Resources에 배치"
else
  echo "  ℹ️ 회계 PEFT 비활성(ACCOUNTING_PEFT_ADAPTER_PATH 미설정, 규칙 기반 계속 사용)"
fi

echo "[4/5] 모델 경로 계약 검증 (verifier)"
python3 "$ROOT/scripts/verify_model_path_contract.py" "$ROOT" || { echo "❌ 계약 위반"; exit 1; }

AUTHORITY_HELPER_ARGS=()
if [[ "$PRODUCTION_A4_AUTHORITY" == "1" ]]; then
  echo "[4.25/5] A4 운영 verifier authority XPC·bridge 조립·분리 서명"
  "$ROOT/scripts/build_a4_authority_helper_macos.sh" --install-helper "$APP" || {
    echo "❌ A4 authority helper 조립 실패 — 운영 A4 비활성"; exit 1;
  }
  AUTHORITY_HELPER_ARGS=(--authority-helper "$AUTHORITY_HELPER_EXE")
else
  rm -rf "$APP/Contents/XPCServices/A4VerifierAuthority.xpc"
  rm -f "$APP/Contents/Resources/butler_pc_core/a4_verifier/libButlerA4AuthorityBridge.dylib"
  echo "[4.25/5] A4 운영 verifier authority 비활성(승인된 인증서·Keychain provisioning 필요)"
fi

BOX5_AUTHORITY_ARGS=()
if [[ "$PRODUCTION_BOX5_AUTHORITY" == "1" ]]; then
  echo "[4.35/5] Box5 사용자 권한 native helper·승인 정책 조립·분리 서명"
  "$ROOT/scripts/build_box5_user_authority_helper_macos.sh" --install-helper "$APP" || {
    echo "❌ Box5 native authority 조립 실패 — 회계 write 및 배포 차단"; exit 1;
  }
  BOX5_AUTHORITY_ARGS=(
    --box5-authority-helper "$BOX5_AUTHORITY_HELPER"
    --box5-authority-policy "$BOX5_AUTHORITY_POLICY"
  )
else
  rm -rf "$RES/box5"
  echo "[4.35/5] Box5 운영 사용자 권한 비활성(승인 정책·인증서·Keychain provisioning 필요)"
fi

echo "[4.5/5] 빌드 표식 기록 (BUILD_INFO.json — 앱 내부 commit OID 표식)"
BUILD_OID="$(cd "$ROOT" && git rev-parse --verify 'HEAD^{commit}' 2>/dev/null)" || {
  echo "❌ git commit OID 확인 실패 — provenance 없는 앱 생성 차단"
  exit 1
}
BUILD_TREE_OID="$(cd "$ROOT" && git rev-parse --verify 'HEAD^{tree}' 2>/dev/null)" || {
  echo "❌ git tree OID 확인 실패 — provenance 없는 앱 생성 차단"
  exit 1
}
BUILD_DESC="$(cd "$ROOT" && git describe --always --dirty 2>/dev/null || echo unknown)"
BUILD_TS="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
APP_VER="$(cd "$ROOT/butler-desktop" && node -p "require('./package.json').version" 2>/dev/null)" || {
  echo "❌ 앱 버전 확인 실패 — provenance 없는 앱 생성 차단"
  exit 1
}
if ! "$APP_PY" "$ROOT/scripts/write_build_info.py" \
  --output "$RES/BUILD_INFO.json" \
  --build-oid "$BUILD_OID" \
  --build-tree-oid "$BUILD_TREE_OID" \
  --git-describe "$BUILD_DESC" \
  --timestamp-utc "$BUILD_TS" \
  --app-version "$APP_VER" \
  ${AUTHORITY_HELPER_ARGS[@]+"${AUTHORITY_HELPER_ARGS[@]}"} \
  ${BOX5_AUTHORITY_ARGS[@]+"${BOX5_AUTHORITY_ARGS[@]}"} \
  ${BUILD_INFO_DISTRIBUTION_ARGS[@]+"${BUILD_INFO_DISTRIBUTION_ARGS[@]}"}; then
  echo "❌ BUILD_INFO.json 기록·검증 실패 — 불완전 앱 생성 차단"
  exit 1
fi
if [[ "$RELEASE_DISTRIBUTION" == "1" ]]; then
  echo "  ✅ BUILD_INFO.json (OID $BUILD_OID · 배포 빌드)"
else
  echo "  ✅ BUILD_INFO.json (OID $BUILD_OID · ★배포용 아님)"
fi

if [[ "$PRODUCTION_A4_AUTHORITY" == "1" ]]; then
  echo "[4.75/5] A4 helper 격리·앱 Hardened Runtime 최종 서명 검증"
  "$ROOT/scripts/build_a4_authority_helper_macos.sh" --finalize-app "$APP" || {
    echo "❌ A4 authority 권한 격리 검증 실패 — 배포 차단"; exit 1;
  }
fi

if [[ "$PRODUCTION_BOX5_AUTHORITY" == "1" ]]; then
  echo "[4.80/5] Box5 helper 격리·정책 digest·앱 Hardened Runtime 최종 검증"
  "$ROOT/scripts/build_box5_user_authority_helper_macos.sh" --finalize-app "$APP" || {
    echo "❌ Box5 authority 권한 격리 검증 실패 — 배포 차단"; exit 1;
  }
fi

echo "[5/5] 완성품 준비 완료"
echo "  앱: $ROOT/butler-desktop/src-tauri/$APP"
echo "  빌드 표식: $RES/BUILD_INFO.json (OID $BUILD_OID)"
echo "  대치: rm -rf /Applications/Butler.app && cp -R '$APP' /Applications/Butler.app"
echo "════════════════════════════════════════"
echo " ✅ Butler 완성품 빌드 완료"
echo "════════════════════════════════════════"
