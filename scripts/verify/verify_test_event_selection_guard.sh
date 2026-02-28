#!/usr/bin/env bash
set -euo pipefail

TEST_EVENT_SELECTION_GUARD_OK=0
cleanup(){ echo "TEST_EVENT_SELECTION_GUARD_OK=${TEST_EVENT_SELECTION_GUARD_OK}"; }
trap cleanup EXIT

# 대상: 백엔드 테스트 코드(필요하면 범위 확장 가능)
ROOT="webcore_appcore_starter_4_17/backend"
test -d "$ROOT" || { echo "BLOCK: missing dir: $ROOT"; exit 1; }

have_rg(){ command -v rg >/dev/null 2>&1 && rg --version >/dev/null 2>&1; }

# 파일 리스트
if have_rg; then
  FILES=($(rg -l --glob '*.test.ts' --glob '*.test.tsx' --glob 'tests/**/*.ts' --glob 'tests/**/*.tsx' -S "." "$ROOT" 2>/dev/null || true))
else
  FILES=($(find "$ROOT" -type f \( -name "*.test.ts" -o -name "*.test.tsx" \) 2>/dev/null || true))
fi

# 스캔 로직: ".find(" 블록을 대충 잡고 reason_code 조건이 나오면 action 조건이 있는지 확인
for f in "${FILES[@]}"; do
  # 빠른 스킵: reason_code 자체가 없으면 패스
  if have_rg; then
    rg -n --no-messages "reason_code\s*===|reason_code\s*==" "$f" >/dev/null 2>&1 || continue
  else
    grep -nE "reason_code[[:space:]]*===|reason_code[[:space:]]*==" "$f" >/dev/null 2>&1 || continue
  fi

  # .find( ... ); 블록 단위로 검사(단순 휴리스틱)
  awk -v FILE="$f" '
    BEGIN{in_find=0; buf=""; start=0}
    {
      line=$0
      if (in_find==0 && line ~ /\.find\(/) { in_find=1; buf=line "\n"; start=NR; next }
      if (in_find==1) {
        buf=buf line "\n"
        if (line ~ /\);\s*$/) {
          # find 블록 종료: reason_code가 있으면 action도 있어야 함
          if (buf ~ /reason_code[[:space:]]*(===|==)/) {
            if (buf !~ /action[[:space:]]*(===|==)/) {
              printf("FAIL: weak .find predicate (reason_code without action) %s:%d-%d\n", FILE, start, NR)
              print buf
              exit 1
            }
          }
          in_find=0; buf=""; start=0
        }
      }
    }
  ' "$f"
done

TEST_EVENT_SELECTION_GUARD_OK=1
exit 0
