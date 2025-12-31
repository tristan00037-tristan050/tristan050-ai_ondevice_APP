#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'USAGE'
R10S7_STEP4B_B_PR_METADATA_GEN.sh

목적:
- Step4-B B PR 메타데이터(Base/Compare/Title/Body)를 "복붙 가능한 완성형"으로 출력한다.
- 기본 동작: PASS Gate를 실행하여 통과(eligible)한 경우에만 PR Body에 증빙(Commit/SSOT/Log/Tail)을 자동 삽입한다.
- PASS Gate 실패 시: PR 메타데이터 출력 자체를 FAIL 처리하여 "증빙 없는 PR 생성"을 구조적으로 차단한다.

옵션:
  --base <branch>        Base 브랜치 (기본: main)
  --title <title>        PR 제목 (기본값 제공)
  --body <file>          PR 본문 SSOT 파일 (기본: docs/ops/R10S7_STEP4B_B_PR_BODY.md)
  --verify <script>      PASS Gate에 넘길 원샷 검증 스크립트 (기본: docs/ops/R10S7_STEP4B_B_ONE_SHOT_PROMPT.sh)
  --ssot <file>          SSOT 증거 파일 (기본: docs/ops/r10-s7-step4b-b-strict-improvement.json)
  --tail <n>             verify 로그 tail 줄 수 (기본: 80)
  --skip-pass-gate       (비권장) PASS Gate 실행 없이 메타데이터만 출력(드래프트용)
  -h|--help              도움말

정본 규칙:
- main 브랜치에서 실행 시 즉시 FAIL(개선 브랜치 강제)
USAGE
}

BASE="main"
TITLE="feat(s7): step4-b-b strict improvement (input-fixed) under regression gate"
BODY_FILE="docs/ops/R10S7_STEP4B_B_PR_BODY.md"

# 기본값: 실제 개선 PR에서는 ONE_SHOT이 가장 안전한 '원샷 검증'으로 쓰임
VERIFY_SCRIPT="docs/ops/R10S7_STEP4B_B_ONE_SHOT_PROMPT.sh"
SSOT_FILE="docs/ops/r10-s7-step4b-b-strict-improvement.json"

TAIL_N=80
RUN_PASS_GATE=1

while [[ $# -gt 0 ]]; do
  case "$1" in
    --base) BASE="$2"; shift 2;;
    --title) TITLE="$2"; shift 2;;
    --body) BODY_FILE="$2"; shift 2;;
    --verify) VERIFY_SCRIPT="$2"; shift 2;;
    --ssot) SSOT_FILE="$2"; shift 2;;
    --tail) TAIL_N="$2"; shift 2;;
    --skip-pass-gate) RUN_PASS_GATE=0; shift 1;;
    -h|--help) usage; exit 0;;
    *) echo "FAIL: unknown arg: $1"; usage; exit 2;;
  esac
done

ROOT="$(git rev-parse --show-toplevel)/webcore_appcore_starter_4_17"
cd "$ROOT"

BRANCH="$(git rev-parse --abbrev-ref HEAD)"
if [[ "$BRANCH" == "$BASE" ]]; then
  echo "FAIL: must run on improvement branch (not $BASE). current=$BRANCH"
  exit 1
fi

PASS_GATE="scripts/ops/verify_pass_gate.sh"
if [[ ! -f "$BODY_FILE" ]]; then
  echo "FAIL: missing PR body SSOT file: $BODY_FILE"
  exit 1
fi
if [[ "$RUN_PASS_GATE" -eq 1 ]]; then
  if [[ ! -f "$PASS_GATE" ]]; then
    echo "FAIL: missing PASS gate script: $PASS_GATE"
    exit 1
  fi
  if [[ ! -f "$VERIFY_SCRIPT" ]]; then
    echo "FAIL: missing verify script: $VERIFY_SCRIPT"
    exit 1
  fi
fi

SHA="$(git rev-parse --short HEAD)"

PASS_STDOUT=""
PASS_STDOUT_SUMMARY=""
PASS_LOG=""
VERIFY_LOG_TAIL=""

if [[ "$RUN_PASS_GATE" -eq 1 ]]; then
  TS="$(python3 - <<'PY'
import time
print(time.strftime("%Y%m%d_%H%M%S", time.localtime()))
PY
)"
  PASS_LOG="/tmp/pass_gate_${TS}.log"

  # PASS Gate 실행(통과 못하면 PR 메타데이터 생성 자체를 중단)
  set +e
  PASS_STDOUT="$(bash "$PASS_GATE" --verify "$VERIFY_SCRIPT" --ssot "$SSOT_FILE" --log "$PASS_LOG" 2>&1)"
  RC=$?
  set -e

  if [[ "$RC" -ne 0 ]]; then
    echo "FAIL: PASS Gate did not pass (rc=$RC). PR metadata generation blocked."
    echo "== PASS GATE STDOUT (tail 200) =="
    printf "%s\n" "$PASS_STDOUT" | tail -n 200 || true
    echo "== VERIFY LOG TAIL (${TAIL_N}) =="
    tail -n "$TAIL_N" "$PASS_LOG" || true
    exit 1
  fi

  # PASS Gate stdout summary (PR Body 과다 방지)
  PASS_STDOUT_SUMMARY="$(
    printf "%s\n" "$PASS_STDOUT" \
    | grep -E "^(== PASS GATE START ==|ROOT=|VERIFY=|SSOT=|LOG=|OK:|FAIL:|PASS:)" \
    | tail -n 80 \
    || true
  )"

  # verify 로그 tail(자동 삽입용)
  VERIFY_LOG_TAIL="$(tail -n "$TAIL_N" "$PASS_LOG" 2>/dev/null || true)"
fi

# ---------- 출력: PR 메타데이터 ----------
echo "Base: $BASE"
echo "Compare: $BRANCH"
echo "Title: $TITLE"
echo "Body:"
echo

# 1) SSOT PR Body 출력
cat "$BODY_FILE"

# 2) 자동 Evidence 블록(정본)
cat <<EOF

---

## PASS Gate Evidence (auto-filled, SSOT)

- Commit: \`$SHA\`
- SSOT evidence: \`$SSOT_FILE\`
- PASS Gate command:
  \`\`\`bash
  bash $PASS_GATE \\
    --verify $VERIFY_SCRIPT \\
    --ssot $SSOT_FILE
  \`\`\`

EOF

if [[ "$RUN_PASS_GATE" -eq 1 ]]; then
  cat <<EOF
- PASS Gate log: \`$PASS_LOG\`

### PASS Gate stdout (summary)
\`\`\`text
$PASS_STDOUT_SUMMARY
\`\`\`

### Verify log tail (last ${TAIL_N} lines)
\`\`\`text
$VERIFY_LOG_TAIL
\`\`\`

EOF
else
  cat <<'EOF'
- Status: PASS Gate was skipped (--skip-pass-gate). This is allowed only for draft.
- Rule: PASS declaration is forbidden unless PASS Gate prints "PASS: CLOSED & SEALED eligible".
EOF
fi

cat <<'EOF'
## Post-merge (main) baseline ratchet (Step4-B B)
- Rule: Step4-B B prohibits --reanchor-input (Plan A only).
- Command (main only):
  ```bash
  bash scripts/ops/prove_update_retriever_baseline.sh --update-baseline --min-gain 0.001
  ```
EOF
