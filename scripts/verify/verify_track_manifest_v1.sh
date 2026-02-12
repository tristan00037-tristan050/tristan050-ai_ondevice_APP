#!/usr/bin/env bash
set -euo pipefail

TRACK_MANIFEST_V1_OK=0
TRACK_MANIFEST_KEYS_EXIST_OK=0
trap 'echo "TRACK_MANIFEST_V1_OK=$TRACK_MANIFEST_V1_OK"; echo "TRACK_MANIFEST_KEYS_EXIST_OK=$TRACK_MANIFEST_KEYS_EXIST_OK"' EXIT

f="docs/ops/contracts/TRACK_MANIFEST_V1.txt"
[ -f "$f" ] || { echo "BLOCK: missing $f"; exit 1; }

# 1) 형식 검사: 빈 줄로 블록 분리, 블록마다 3줄 세트 필수
awk '
  BEGIN{tid=0;pr=0;rk=0;inblk=0}
  /^TRACK_ID=/{tid=1; inblk=1}
  /^PR=/{pr=1; inblk=1}
  /^REQUIRED_KEYS=/{rk=1; inblk=1}
  /^$/{ if(inblk==1){ if(tid+pr+rk!=3) exit 2; tid=0;pr=0;rk=0; inblk=0 } }
  END{ if(inblk==1 && tid+pr+rk!=3) exit 2 }
' "$f" || { echo "BLOCK: invalid TRACK_MANIFEST_V1 format"; exit 1; }

# PR 숫자 검사 (모든 PR 라인이 숫자여야 함)
grep -qE '^PR=[0-9]+$' "$f" || { echo "BLOCK: PR must be numeric"; exit 1; }

TRACK_MANIFEST_V1_OK=1

# 2) REQUIRED_KEYS가 "레포에서 실제로 출력될 근거"가 있는지 정적 확인 (재귀 금지)
# - docs 제외
# - scripts/verify 및 scripts/ai 안에서 찾음 (키들은 verify 스크립트들이 trap으로 echo "KEY=..." 형태로 출력)
keys="$(grep '^REQUIRED_KEYS=' "$f" | cut -d= -f2 | tr ',' '\n' | sed '/^$/d' | sort -u)"
[ -n "$keys" ] || { echo "BLOCK: REQUIRED_KEYS empty"; exit 1; }

for k in $keys; do
  # KEY= 형태가 scripts/verify 또는 scripts/ai 내 어디엔가 존재해야 함 (fail-closed)
  # echo "KEY=..." 또는 KEY= 형태 모두 허용
  if ! (find scripts/verify scripts/ai -type f -name '*.sh' -print0 2>/dev/null | xargs -0 grep -qE "(^${k}=|[\"']${k}=)" 2>/dev/null); then
    echo "BLOCK: required key has no emitter in scripts/verify or scripts/ai: ${k}"
    exit 1
  fi
done

TRACK_MANIFEST_KEYS_EXIST_OK=1
exit 0
