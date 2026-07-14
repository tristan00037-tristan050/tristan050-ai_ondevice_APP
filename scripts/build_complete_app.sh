#!/bin/bash
# Butler 완성품 빌드 — 한 번에 조립되는 완전한 앱
# 부품을 매번 급조하지 않도록, 빌드+llama-cpp+모델확인+검증을 1개 스크립트로.
set -uo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT/butler-desktop/src-tauri"
APP="target/release/bundle/macos/Butler.app"
RES="$APP/Contents/Resources"

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
ACC_SRC="$HOME/Desktop/butler-data/엔진모델/회계어댑터_박스5/qwen3_4b_accounting_v1"
ACC_DST="$ROOT/butler_pc_core/accounting/models/qwen3_4b_accounting_v1"
if [[ -d "$ACC_SRC" && ! -d "$ACC_DST" ]]; then
  mkdir -p "$(dirname "$ACC_DST")"; cp -R "$ACC_SRC" "$ACC_DST"
  echo "  ✅ 회계 adapter 배치"
elif [[ -d "$ACC_DST" ]]; then echo "  ✅ 회계 adapter 이미 존재"
else echo "  ⚠️ 회계 adapter 소스 없음 (별건)"; fi

echo "[4/5] 모델 경로 계약 검증 (verifier)"
python3 "$ROOT/scripts/verify_model_path_contract.py" "$ROOT" || { echo "❌ 계약 위반"; exit 1; }

echo "[4.5/5] 빌드 표식 기록 (BUILD_INFO.json — 앱 내부 commit OID 표식)"
BUILD_OID="$(cd "$ROOT" && git rev-parse HEAD 2>/dev/null || echo unknown)"
BUILD_DESC="$(cd "$ROOT" && git describe --always --dirty 2>/dev/null || echo unknown)"
BUILD_TS="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
APP_VER="$(cd "$ROOT/butler-desktop" && node -p "require('./package.json').version" 2>/dev/null || echo unknown)"
cat > "$RES/BUILD_INFO.json" <<JSON
{
  "app": "Butler",
  "build_base_commit_oid": "$BUILD_OID",
  "git_describe": "$BUILD_DESC",
  "build_timestamp_utc": "$BUILD_TS",
  "app_version": "$APP_VER",
  "builder": "build_complete_app.sh"
}
JSON
[[ "$BUILD_OID" != "unknown" ]] && echo "  ✅ BUILD_INFO.json (OID $BUILD_OID)" || echo "  ⚠️ git OID 확인불가 — BUILD_INFO.json에 unknown 기록"

echo "[5/5] 완성품 준비 완료"
echo "  앱: $ROOT/butler-desktop/src-tauri/$APP"
echo "  빌드 표식: $RES/BUILD_INFO.json (OID $BUILD_OID)"
echo "  대치: rm -rf /Applications/Butler.app && cp -R '$APP' /Applications/Butler.app"
echo "════════════════════════════════════════"
echo " ✅ Butler 완성품 빌드 완료"
echo "════════════════════════════════════════"
