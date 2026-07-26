#!/bin/bash
# ============================================================
#  ★★★ 복사 직후 제일 먼저 이 파일을 실행하세요 ★★★
#
#  실행:  bash 권한복구.sh
#  (또는 폴더에서 더블클릭이 안 되면 터미널에 위 명령을 입력)
#
#  왜 필요한가요?
#   - 이 인계 폴더는 T7 외장(exFAT, noowners)에 담겨 왔습니다.
#     exFAT 에서는 chmod(권한)가 무의미해서, 만든 쪽에서 권한을 맞춰도
#     의미가 없습니다.
#   - 그런데 이 폴더를 맥 내장 디스크로 복사하면, 파일에 700(소유자
#     전용) 권한이 따라붙어 스크립트 실행·도구 사용·공유가 막힙니다.
#   - 이 스크립트가 폴더 전체 권한을 정상값으로 되돌립니다.
#
#  ※ 2026-07-17 그룹A 지적 수정본:
#     예전 판은 모든 파일을 644 로 만든 뒤 .sh/.py 만 755 로 되돌렸습니다.
#     그래서 Butler.app/Contents/MacOS/butler-desktop 처럼 ★확장자가 없는
#     실행 파일이 644 로 남아 앱이 아예 열리지 않았습니다.
#     이제 실행 파일을 확장자가 아니라 ★내용(Mach-O·ELF·shebang)과
#     경로(MacOS/·bin/ 등)로 판별해 되돌립니다.
# ============================================================
set -euo pipefail

RAW_TARGET="${1:-$(cd "$(dirname "$0")" && pwd)}"

refuse() {
  echo "❌ 권한 복구를 거부합니다: $1"
  echo "   이 스크립트는 폴더 전체 권한을 재귀적으로 바꿉니다."
  echo "   인계 패키지 폴더만 대상으로 삼습니다."
  exit 1
}

# ── 0) 대상 검증 ─────────────────────────────────────────────
#    재귀 chmod 는 잘못된 대상에 걸리면 사용자 파일 권한을 광범위하게 파괴하거나
#    노출한다(644 는 다른 사용자에게 읽기 허용). 대상을 좁게 강제한다.
[ -L "$RAW_TARGET" ] && refuse "심볼릭 링크는 대상이 될 수 없습니다 — $RAW_TARGET"
[ -d "$RAW_TARGET" ] || { echo "❌ 대상 폴더가 없습니다: $RAW_TARGET"; exit 1; }
TARGET="$(cd "$RAW_TARGET" && pwd -P)"

[ "$TARGET" = "/" ] && refuse "루트 디렉터리(/)"
[ "$(dirname "$TARGET")" = "/" ] && refuse "최상위 디렉터리 — $TARGET"
if [ -n "${HOME:-}" ] && [ -d "$HOME" ]; then
  [ "$TARGET" = "$(cd "$HOME" && pwd -P)" ] && refuse "홈 디렉터리 — $TARGET"
fi
[ -e "$TARGET/.git" ] && refuse "git 저장소 루트 — $TARGET"

# 인계 패키지 표식이 있어야 한다. 아무 폴더에나 걸리지 않게 하는 마지막 방어선이다.
marker=""
if find "$TARGET" -type d -path '*/Butler.app/Contents/MacOS' -print -quit 2>/dev/null | grep -q .; then
  marker="Butler.app/Contents/MacOS"
else
  for candidate in HANDOFF_MANIFEST.json handoff_manifest.json; do
    if [ -f "$TARGET/$candidate" ]; then
      marker="$candidate"
      break
    fi
  done
fi
[ -n "$marker" ] || refuse "인계 패키지 표식이 없습니다 — $TARGET
   필요한 표식: Butler.app/Contents/MacOS 디렉터리, 또는 최상위의 HANDOFF_MANIFEST.json"

echo "권한 복구 대상 폴더: $TARGET"
echo "인계 패키지 표식: $marker"

# ── 1) 기본값: 디렉터리 755 · 파일 644 ────────────────────────
# -exec ... + 로 묶어 실행한다(파일 하나당 chmod 한 번씩 부르지 않는다).
find "$TARGET" -type d -exec chmod 755 {} +
find "$TARGET" -type f -exec chmod 644 {} +

# ── 2) 확장자로 명백한 실행 스크립트 ──────────────────────────
find "$TARGET" -type f \( \
  -name '*.sh' -o -name '*.py' -o -name '*.command' -o \
  -name '*.pl' -o -name '*.rb' -o -name '*.bash' -o -name '*.zsh' \
  \) -exec chmod 755 {} +

# ── 3) 실행 파일이 놓이는 표준 경로 ───────────────────────────
#    .app 번들의 실행부와 런타임 bin 은 확장자가 없는 경우가 대부분이다.
find "$TARGET" -type f \( \
  -path '*/Contents/MacOS/*' -o -path '*/bin/*' -o -path '*/sbin/*' -o \
  -path '*/libexec/*' -o -path '*/binaries/*' \
  \) -exec chmod 755 {} +

# ── 4) 내용으로 판별: 확장자가 없거나 바이너리 계열인 파일 ────
#    ★이번 버그의 핵심. 확장자에 기대지 않고 매직넘버/shebang 을 본다.
is_executable_payload() {
  local path="$1" magic shebang
  # Mach-O(32/64, BE/LE) · universal(fat 32/64, BE/LE) · ELF
  #   feedface/feedfacf : MH_MAGIC / MH_MAGIC_64
  #   cefaedfe/cffaedfe : MH_CIGAM / MH_CIGAM_64
  #   cafebabe/bebafeca : FAT_MAGIC / FAT_CIGAM
  #   cafebabf/bfbafeca : FAT_MAGIC_64 / FAT_CIGAM_64  ← 64비트 universal 바이너리
  #   7f454c46          : ELF
  magic="$(head -c 4 "$path" 2>/dev/null | od -An -v -tx1 | tr -d ' \n')"
  case "$magic" in
    feedface|feedfacf|cefaedfe|cffaedfe) return 0 ;;
    cafebabe|bebafeca|cafebabf|bfbafeca) return 0 ;;
    7f454c46) return 0 ;;
  esac
  # #! 로 시작하는 스크립트
  shebang="$(head -c 2 "$path" 2>/dev/null || true)"
  [ "$shebang" = "#!" ] && return 0
  return 1
}

restored=0
while IFS= read -r candidate; do
  if is_executable_payload "$candidate"; then
    chmod 755 "$candidate"
    restored=$((restored + 1))
  fi
done <<EOF
$(find "$TARGET" -type f ! -perm -u+x \( \
    ! -name '*.*' -o \
    -name '*.dylib' -o -name '*.so' -o -name '*.bundle' -o \
    -name '*.node' -o -name '*.bin' -o -name '*.out' \
  \) 2>/dev/null)
EOF

# ── 5) 자기 점검: 앱 실행부가 실행 가능한 상태로 남았는가 ─────
broken=0
while IFS= read -r must_run; do
  [ -z "$must_run" ] && continue
  if [ ! -x "$must_run" ]; then
    echo "❌ 실행 권한이 복구되지 않았습니다: $must_run"
    broken=$((broken + 1))
  fi
done <<EOF
$(find "$TARGET" -type f -path '*/Contents/MacOS/*' 2>/dev/null)
EOF
if [ "$broken" -gt 0 ]; then
  echo "❌ 앱 실행부 $broken 개가 실행 불가 상태입니다 — 이 폴더로는 앱이 열리지 않습니다."
  exit 1
fi

echo "✅ 권한 복구 완료 — 디렉터리 755 · 문서 644 · 실행 파일 755"
echo "   내용으로 판별해 되살린 실행 파일: ${restored}개(확장자 없는 실행 파일 포함)"
echo "   이제 00_먼저읽기.md 를 열어 보세요."
