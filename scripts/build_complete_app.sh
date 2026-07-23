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

echo "════════════════════════════════════════"
echo " Butler 완성품 빌드 시작"
echo "════════════════════════════════════════"

echo "[1/5] Tauri 빌드 (.app)"
# pipefail(4행)로 npm 실패는 파이프 종료코드에 반영된다. 과거 `|| true` 가 이를 가려
# beforeBuildCommand(build_runtime.sh) 실패 시 STALE 번들을 성공으로 오인했다 — 제거한다.
( cd "$ROOT/butler-desktop" && npm run tauri build 2>&1 | tail -30 )
TAURI_RC=$?
[[ $TAURI_RC -eq 0 ]] || { echo "❌ tauri build 실패 (exit $TAURI_RC) — STALE 번들 방지 위해 중단"; exit 1; }
[[ -d "$APP" ]] || { echo "❌ .app 생성 실패"; exit 1; }
echo "  ✅ .app 생성"

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
  "${AUTHORITY_HELPER_ARGS[@]}"; then
  echo "❌ BUILD_INFO.json 기록·검증 실패 — 불완전 앱 생성 차단"
  exit 1
fi
echo "  ✅ BUILD_INFO.json (OID $BUILD_OID)"

if [[ "$PRODUCTION_A4_AUTHORITY" == "1" ]]; then
  echo "[4.75/5] A4 helper 격리·앱 Hardened Runtime 최종 서명 검증"
  "$ROOT/scripts/build_a4_authority_helper_macos.sh" --finalize-app "$APP" || {
    echo "❌ A4 authority 권한 격리 검증 실패 — 배포 차단"; exit 1;
  }
fi

echo "[5/5] 완성품 준비 완료"
echo "  앱: $ROOT/butler-desktop/src-tauri/$APP"
echo "  빌드 표식: $RES/BUILD_INFO.json (OID $BUILD_OID)"
echo "  대치: rm -rf /Applications/Butler.app && cp -R '$APP' /Applications/Butler.app"
echo "════════════════════════════════════════"
echo " ✅ Butler 완성품 빌드 완료"
echo "════════════════════════════════════════"
