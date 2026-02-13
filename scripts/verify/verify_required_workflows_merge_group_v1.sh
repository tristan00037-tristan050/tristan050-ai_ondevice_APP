#!/usr/bin/env bash
set -euo pipefail

REQUIRED_WORKFLOWS_LIST_V1_OK=0
WORKFLOW_MERGE_GROUP_COVERAGE_V1_OK=0
trap 'echo "REQUIRED_WORKFLOWS_LIST_V1_OK=$REQUIRED_WORKFLOWS_LIST_V1_OK"; echo "WORKFLOW_MERGE_GROUP_COVERAGE_V1_OK=$WORKFLOW_MERGE_GROUP_COVERAGE_V1_OK"' EXIT

f="docs/ops/contracts/REQUIRED_WORKFLOWS_LIST_V1.txt"
[ -f "$f" ] || { echo "BLOCK: missing $f"; exit 1; }
grep -q "REQUIRED_WORKFLOWS_LIST_V1_TOKEN=1" "$f" || { echo "BLOCK: token missing"; exit 1; }
REQUIRED_WORKFLOWS_LIST_V1_OK=1

# on: 블록 내부에서만 merge_group 존재를 인정하는 판정기
# - YAML 파서 의존 금지(POSIX)
# - on: [..] 형태와 on: 아래 매핑/리스트 형태 모두 지원
has_merge_group_in_on_block() {
  file="$1"
  awk '
    BEGIN{
      in_on=0; on_indent=-1; found=0;
    }
    function ltrim(s){ sub(/^[ \t]+/, "", s); return s }
    function indent(s,  m){ match(s, /^[ \t]*/); return RLENGTH }

    {
      raw=$0

      # 주석만인 라인 무시
      if (raw ~ /^[ \t]*#/) next

      # 빈 줄은 on 블록 종료 조건으로 쓰지 않음(들여쓰기 유지 가능)
      # 단, on: [..] 형태는 한 줄에서 바로 판단 가능
      if (raw ~ /^[ \t]*on:[ \t]*\[/) {
        line=raw
        gsub(/#.*/, "", line)               # trailing comment 제거
        gsub(/^[ \t]*on:[ \t]*\[/, "", line)
        gsub(/\][ \t]*$/, "", line)
        gsub(/[ \t]/, "", line)
        n=split(line, arr, ",")
        for(i=1;i<=n;i++){
          if(arr[i]=="merge_group"){ found=1 }
        }
        next
      }

      # on: 시작(매핑)
      if (raw ~ /^[ \t]*on:[ \t]*$/) {
        in_on=1
        on_indent=indent(raw)
        next
      }

      # on 블록 안에서만 검사
      if (in_on==1) {
        cur_indent=indent(raw)

        # 들여쓰기 감소(또는 같은 레벨의 다른 top key)면 on 블록 종료
        if (cur_indent <= on_indent && raw ~ /^[^ \t]/) { in_on=0 }
        if (cur_indent <= on_indent && raw ~ /^[ \t]*[A-Za-z0-9_-]+:[ \t]*$/) { in_on=0 }

        if (in_on==0) next

        line=raw
        gsub(/#.*/, "", line)               # comment 제거
        line=ltrim(line)

        # on 블록의 최상위 이벤트 키: merge_group:
        if (line ~ /^merge_group:[ \t]*$/) { found=1; next }

        # on 블록에서 리스트 형태로 이벤트 나열:
        # - merge_group
        if (line ~ /^-[ \t]*merge_group[ \t]*$/) { found=1; next }

        # on 블록에서 키: 값 형태로 한 줄로 쓰는 경우는 드묾이지만 대응
        if (line ~ /^merge_group[ \t]*:/) { found=1; next }
      }
    }
    END{
      if(found==1) exit 0
      exit 1
    }
  ' "$file"
}

bad=0
while IFS= read -r line; do
  wf="$(echo "$line" | sed 's/^WORKFLOW=//')"
  file=".github/workflows/${wf}.yml"
  [ -f "$file" ] || { echo "BLOCK: missing workflow file $file"; exit 1; }

  if ! has_merge_group_in_on_block "$file"; then
    echo "BLOCK: merge_group trigger missing under on: in $file"
    bad=1
  fi
done < <(grep '^WORKFLOW=' "$f")

[ "$bad" = "0" ] || exit 1

WORKFLOW_MERGE_GROUP_COVERAGE_V1_OK=1
exit 0
