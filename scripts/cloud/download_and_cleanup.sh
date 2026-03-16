#!/usr/bin/env bash
# =============================================================================
# download_and_cleanup.sh — 모델 압축 + 다운로드 안내
#
# ⚠️  이 스크립트는 서버를 삭제하지 않습니다.
#     압축 파일 다운로드 후 반드시 사람이 직접 서버를 삭제해 주세요!
# =============================================================================
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$REPO_ROOT"

OUTPUT_DIR="output/butler_model_v1"
ARCHIVE_NAME="butler_model_v1.tar.gz"

echo "=============================================="
echo " 모델 압축 및 다운로드 준비"
echo "=============================================="
echo ""

# ── 출력 폴더 확인 ───────────────────────────────────────────────────────────
if [ ! -d "$OUTPUT_DIR" ]; then
    echo "❌ 모델 폴더가 없습니다: $OUTPUT_DIR"
    echo "   run_training.sh 를 먼저 실행해 주세요."
    exit 1
fi

FILE_COUNT=$(find "$OUTPUT_DIR" -type f | wc -l | tr -d ' ')
if [ "$FILE_COUNT" -eq 0 ]; then
    echo "❌ $OUTPUT_DIR 폴더가 비어 있습니다."
    echo "   run_training.sh 를 먼저 실행해 주세요."
    exit 1
fi

echo "  ✅ 모델 폴더 확인: $OUTPUT_DIR ($FILE_COUNT 개 파일)"
echo ""

# ── 압축 ─────────────────────────────────────────────────────────────────────
echo "[1/2] $ARCHIVE_NAME 으로 압축 중..."
echo "  ※ 파일 크기에 따라 수 분 걸릴 수 있습니다."
echo ""

tar -czvf "$ARCHIVE_NAME" "$OUTPUT_DIR"

ARCHIVE_SIZE=$(du -sh "$ARCHIVE_NAME" | cut -f1)
echo ""
echo "  ✅ 압축 완료: $ARCHIVE_NAME ($ARCHIVE_SIZE)"
echo ""

# ── 무결성 체크섬 생성 ────────────────────────────────────────────────────────
echo "[2/2] SHA256 체크섬 생성 중..."
shasum -a 256 "$ARCHIVE_NAME" > "${ARCHIVE_NAME}.sha256"
cat "${ARCHIVE_NAME}.sha256"
echo "  ✅ 체크섬 저장: ${ARCHIVE_NAME}.sha256"
echo ""

# ── 다운로드 안내 ─────────────────────────────────────────────────────────────
echo "=============================================="
echo " 이제 이 파일을 다운로드하고 서버를 삭제하세요! 🎉"
echo "=============================================="
echo ""
echo " 📥 다운로드할 파일:"
echo "    $(pwd)/$ARCHIVE_NAME"
echo "    $(pwd)/${ARCHIVE_NAME}.sha256"
echo ""
echo " 💻 로컬 PC에서 다운로드하는 방법 (터미널에서):"
echo "    scp root@<서버IP>:$(pwd)/$ARCHIVE_NAME ./"
echo "    scp root@<서버IP>:$(pwd)/${ARCHIVE_NAME}.sha256 ./"
echo ""
echo " 또는 네이버클라우드 Object Storage에 업로드:"
echo "    aws s3 cp $ARCHIVE_NAME s3://<버킷명>/ --endpoint-url https://kr.object.ncloudstorage.com"
echo ""
echo "======================================================"
echo " ⚠️  경고: 다운로드가 완료되면 반드시 GPU 서버를 삭제하세요!"
echo " ⚠️  서버를 켜두면 요금이 계속 발생합니다!"
echo " ⚠️  삭제 방법: NCLOUD_GUIDE.md 의 [STEP 7] 참고"
echo "======================================================"
echo ""
echo " ✅ 다운로드 완료 확인 방법 (로컬 PC에서):"
echo "    shasum -a 256 $ARCHIVE_NAME"
echo "    → 위 체크섬 값과 일치하면 파일이 정상입니다."
echo ""
