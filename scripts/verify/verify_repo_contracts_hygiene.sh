#!/usr/bin/env bash
set -euo pipefail

ROOT="$(git rev-parse --show-toplevel)"
cd "$ROOT"

TARGET="scripts/verify/verify_repo_contracts.sh"
test -s "$TARGET" || { echo "BLOCK: missing $TARGET"; exit 1; }

# 1) *_OK=0 중복 선언 탐지
DUPES="$(
  rg -n '^[A-Z0-9_]+_OK=0$' "$TARGET" \
  | sed -E 's/^[0-9]+:([^=]+)=0$/\1/' \
  | sort | uniq -d
)"
if [[ -n "${DUPES}" ]]; then
  echo "FAIL: duplicate *_OK=0 declarations found:"
  echo "$DUPES"
  exit 1
fi

# 2) 선언된 *_OK가 cleanup에서 echo되는지 누락 탐지
DECLS="$(
  rg -n '^[A-Z0-9_]+_OK=0$' "$TARGET" \
  | sed -E 's/^[0-9]+:([^=]+)=0$/\1/' \
  | sort -u
)"
MISSED=""
while IFS= read -r k; do
  [[ -z "$k" ]] && continue
  # 패턴: echo "KEY=${KEY}" (변수 확장)
  # rg에서 변수 확장을 피하기 위해 --fixed-strings 사용 불가 (패턴이 복잡함)
  # 대신 KEY= 패턴으로 검색 (echo 다음에 KEY=가 오는지)
  # rg의 .*는 정규식이므로 이스케이프 필요 없음
  if ! rg -n "echo.*${k}.*=" "$TARGET" >/dev/null 2>&1; then
    MISSED="${MISSED}${k}"$'\n'
  fi
done <<< "$DECLS"
if [[ -n "${MISSED}" ]]; then
  echo "FAIL: declared keys not echoed in cleanup():"
  echo "$MISSED"
  exit 1
fi

# 3) run_guard 대상 스크립트 실존/경로 오타 탐지
#    패턴: run_guard "name" bash <path>
MISSING_SCRIPTS=""
while IFS= read -r line; do
  # line 예: run_guard "xxx" bash scripts/verify/verify_xxx.sh
  p="$(echo "$line" | sed -E 's/.* bash ([^ ]+).*/\1/')"
  if [[ -z "$p" || "$p" == "$line" ]]; then
    continue
  fi
  if [[ ! -f "$p" ]]; then
    MISSING_SCRIPTS="${MISSING_SCRIPTS}${p}"$'\n'
  fi
done < <(rg -n '^run_guard\s+".*"\s+bash\s+[^ ]+' "$TARGET" | sed -E 's/^[0-9]+://')

if [[ -n "${MISSING_SCRIPTS}" ]]; then
  echo "FAIL: run_guard references missing scripts:"
  echo "$MISSING_SCRIPTS"
  exit 1
fi

# 4) 무출력 통과 차단(최소 출력 패턴 검사)
#    허용 패턴: _OK= 또는 echo "OK"
NO_OUTPUT_SCRIPTS=""
while IFS= read -r line; do
  p="$(echo "$line" | sed -E 's/.* bash ([^ ]+).*/\1/')"
  [[ -z "$p" || "$p" == "$line" ]] && continue
  if ! rg -n '(_OK=|echo\s+"OK")' "$p" >/dev/null; then
    NO_OUTPUT_SCRIPTS="${NO_OUTPUT_SCRIPTS}${p}"$'\n'
  fi
done < <(rg -n '^run_guard\s+".*"\s+bash\s+[^ ]+' "$TARGET" | sed -E 's/^[0-9]+://')

if [[ -n "${NO_OUTPUT_SCRIPTS}" ]]; then
  echo "FAIL: guard scripts without minimal output markers (_OK= or echo \"OK\"):"
  echo "$NO_OUTPUT_SCRIPTS"
  exit 1
fi

echo "REPO_CONTRACTS_HYGIENE_OK=1"
exit 0

