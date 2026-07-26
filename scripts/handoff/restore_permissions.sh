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
#
# ★표식은 TARGET 루트에 ★직접 있어야 한다. 하위 트리를 뒤지면 인계 폴더의 한 칸 위를
#   TARGET 으로 넣어도 아래쪽 Butler.app 때문에 통과해 버리고, 그 위 폴더 전체가
#   chmod 된다(옆에 있던 개인 자료가 0644 로 열린다). 재귀 검색을 쓰지 않는다.
#
# manifest 경로도 ★파일 존재만으로 승인하지 않는다. 빈 {} 를 아무 폴더에나 두면
# 통과해 버리기 때문이다. 아래를 전부 만족해야 표식으로 인정한다.
#   · JSON 이고 schema_version 이 butler.handoff.manifest.v1
#   · package_root 가 canonical TARGET 의 이름과 일치
#   · app_paths 가 1개 이상이며 전부 허용된 상대 경로
#   · 경로에 .. / 절대경로 / symlink 가 없고, 해석 결과가 TARGET 안에 머무름
#   · 각 경로가 실제 존재하는 .app 이고 Contents/MacOS 를 가짐

MANIFEST_SCHEMA_VERSION="butler.handoff.manifest.v1"
MANIFEST_PARSER=""

manifest_field() {
  # $1=파일 $2=키 — 문자열 값이 없거나 타입/JSON 이 잘못됐으면 실패한다.
  if [ "$MANIFEST_PARSER" = "plutil" ]; then
    plutil -extract "$2" raw -expect string -o - "$1" 2>/dev/null
    return
  fi
  python3 - "$1" "$2" 2>/dev/null <<'PY'
import json
import sys

path, key_path = sys.argv[1:3]
with open(path, "r", encoding="utf-8") as stream:
    value = json.load(stream)
for component in key_path.split("."):
    if isinstance(value, dict):
        value = value[component]
    elif isinstance(value, list) and component.isdecimal():
        value = value[int(component)]
    else:
        raise KeyError(component)
if not isinstance(value, str):
    raise TypeError("manifest field must be a string")
sys.stdout.write(value)
PY
}

manifest_app_paths_count() {
  local path="$1"
  if [ "$MANIFEST_PARSER" = "plutil" ]; then
    plutil -extract app_paths raw -expect array -o - "$path" 2>/dev/null
    return
  fi
  python3 - "$path" 2>/dev/null <<'PY'
import json
import sys

with open(sys.argv[1], "r", encoding="utf-8") as stream:
    value = json.load(stream)
app_paths = value.get("app_paths") if isinstance(value, dict) else None
if not isinstance(app_paths, list):
    raise TypeError("app_paths must be an array")
sys.stdout.write(str(len(app_paths)))
PY
}

reject_manifest() {
  refuse "인계 manifest 가 유효하지 않습니다 — $1
   manifest 는 다음을 만족해야 합니다.
   · schema_version = \"$MANIFEST_SCHEMA_VERSION\"
   · package_root   = \"$(basename "$TARGET")\"  (대상 폴더 이름과 일치)
   · app_paths      = 대상 폴더 기준 상대 경로 1개 이상(.app 디렉터리)
   절대경로·..·symlink 는 허용하지 않습니다."
}

validate_relative_app_path() {
  local relative="$1" component accumulated resolved
  [ -n "$relative" ] || reject_manifest "app_paths 에 빈 경로가 있습니다"
  case "$relative" in
    /*) reject_manifest "절대 경로는 허용하지 않습니다 — $relative" ;;
    *[\\]*) reject_manifest "역슬래시 경로는 허용하지 않습니다 — $relative" ;;
  esac
  accumulated="$TARGET"
  local saved_ifs="$IFS"
  IFS='/'
  # shellcheck disable=SC2086
  set -- $relative
  IFS="$saved_ifs"
  for component in "$@"; do
    case "$component" in
      ""|"."|"..") reject_manifest "상대 경로에 . 또는 .. 를 쓸 수 없습니다 — $relative" ;;
    esac
    accumulated="$accumulated/$component"
    [ -L "$accumulated" ] && reject_manifest "경로에 symlink 가 있습니다 — $relative"
    [ -e "$accumulated" ] || reject_manifest "경로가 존재하지 않습니다 — $relative"
  done
  [ -d "$accumulated" ] || reject_manifest "디렉터리가 아닙니다 — $relative"
  resolved="$(cd "$accumulated" && pwd -P)"
  case "$resolved" in
    "$TARGET"/*) ;;
    *) reject_manifest "대상 폴더 밖을 가리킵니다 — $relative" ;;
  esac
  [ -d "$accumulated/Contents/MacOS" ] \
    || reject_manifest "앱 번들이 아닙니다(Contents/MacOS 없음) — $relative"
}

validate_manifest() {
  local path="$1" value count index
  [ -L "$path" ] && reject_manifest "manifest 가 symlink 입니다"
  if command -v plutil >/dev/null 2>&1; then
    MANIFEST_PARSER="plutil"
  elif command -v python3 >/dev/null 2>&1; then
    MANIFEST_PARSER="python3"
  else
    refuse "manifest 검증 도구(plutil 또는 python3)를 찾을 수 없습니다 — 검증 없이 진행하지 않습니다"
  fi

  value="$(manifest_field "$path" schema_version)" \
    || reject_manifest "JSON 이 아니거나 schema_version 이 없습니다"
  [ "$value" = "$MANIFEST_SCHEMA_VERSION" ] \
    || reject_manifest "schema_version 이 다릅니다 — $value"

  value="$(manifest_field "$path" package_root)" \
    || reject_manifest "package_root 가 없습니다"
  case "$value" in
    ""|*/*|.|..) reject_manifest "package_root 형식이 잘못됐습니다 — $value" ;;
  esac
  [ "$value" = "$(basename "$TARGET")" ] \
    || reject_manifest "package_root 가 대상 폴더와 다릅니다 — manifest=$value 대상=$(basename "$TARGET")"

  count="$(manifest_app_paths_count "$path")" \
    || reject_manifest "app_paths 가 배열이 아닙니다"
  case "$count" in
    ""|*[!0-9]*) reject_manifest "app_paths 길이를 확인할 수 없습니다" ;;
  esac
  [ "$count" -ge 1 ] || reject_manifest "app_paths 가 비어 있습니다"
  [ "$count" -le 64 ] || reject_manifest "app_paths 가 너무 많습니다"
  index=0
  while [ "$index" -lt "$count" ]; do
    value="$(manifest_field "$path" "app_paths.$index")" \
      || reject_manifest "app_paths 항목은 문자열이어야 합니다 — index=$index"
    validate_relative_app_path "$value"
    index=$((index + 1))
  done
}

marker=""
if [ -d "$TARGET/Butler.app/Contents/MacOS" ]; then
  marker="Butler.app/Contents/MacOS"
else
  for candidate in HANDOFF_MANIFEST.json handoff_manifest.json; do
    if [ -f "$TARGET/$candidate" ]; then
      validate_manifest "$TARGET/$candidate"
      marker="$candidate (검증됨)"
      break
    fi
  done
fi
[ -n "$marker" ] || refuse "인계 패키지 표식이 없습니다 — $TARGET
   표식은 대상 폴더 ★바로 아래에 있어야 합니다(하위 폴더는 보지 않습니다).
   · $TARGET/Butler.app/Contents/MacOS  디렉터리, 또는
   · $TARGET/HANDOFF_MANIFEST.json      파일
   앱이 하위 폴더(예: 01_앱/Butler.app)에 있는 패키지라면 패키지 최상위에
   HANDOFF_MANIFEST.json 을 두고 그 폴더를 대상으로 지정하십시오."

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
