# S7 Step4-B B 실제 개선 PR 실행 순서 (정본)

## 개요

본 가이드는 **S7 Step4-B B(입력 고정 알고리즘 개선 PR)**의 전체 실행 순서를 정본으로 정의합니다.

**성공 기준 (정본):**
- Regression Gate PASS
- Strict improvement ≥ 1 (JSON 정본 증빙)
- meta-only PASS + proof/.latest + META_ONLY_DEBUG 유지

---

## 실행 순서 (6단계)

### 1) 개선 브랜치 생성

```bash
set -euo pipefail
cd "$(git rev-parse --show-toplevel)/webcore_appcore_starter_4_17"

git checkout main
git pull --ff-only

# 브랜치명은 팀 컨벤션대로 (예시)
git checkout -b feat/s7-step4b-b-algo-improve
```

### 2) 알고리즘 변경

**절대 변경 금지:**
- `docs/ops/r10-s7-retriever-goldenset.jsonl`
- `docs/ops/r10-s7-retriever-corpus.jsonl`
- `docs/ops/r10-s7-retriever-metrics-baseline.json`

**변경 범위:**
- 입력 고정 알고리즘 범위로만 제한
  - ranker/tiebreak/정렬/평가 스크립트 등
  - 예: `scripts/ops/eval_retriever_quality_phase1.sh`

### 3) PR 생성 전 Preflight + PR 메타 자동 출력

```bash
set -euo pipefail
cd "$(git rev-parse --show-toplevel)/webcore_appcore_starter_4_17"

bash docs/ops/R10S7_STEP4B_B_PR_METADATA_GEN.sh
```

**출력 확인:**
- `OK: input-fixed + baseline unchanged` 출력일 때만 PR 생성 진행
- Base/Compare/Title/Body가 함께 출력되면 그대로 PR에 복붙

**Preflight 실패 시:**
- 입력 변경 또는 baseline 변경이 감지되면 즉시 FAIL
- 변경 사항을 되돌리고 재시도

### 4) 로컬에서 "Gate PASS + Strict Improvement JSON 증빙" 생성

SSOT 패키지에 봉인된 원샷을 그대로 사용합니다.

```bash
set -euo pipefail
cd "$(git rev-parse --show-toplevel)/webcore_appcore_starter_4_17"

bash docs/ops/R10S7_STEP4B_B_ONE_SHOT_PROMPT.sh
```

**성공 기준 (정본):**
- Regression Gate PASS
- Strict improvement ≥ 1 (JSON 정본 증빙)
- meta-only PASS + proof/.latest + META_ONLY_DEBUG 유지

**실패 시:**
- 알고리즘 로직만 조정 (입력/baseline은 절대 변경 금지)
- 재시도

### 5) PR 생성

**Preflight가 출력한 Base/Compare/Title/Body를 그대로 사용 (복붙 실수 제거)**

**CI에서 확인:**
- Regression Gate 필수 실행 + PASS
- meta-only PASS
- 입력 변경 분기(Data Expansion Gate)로 들어가면 안 됨

### 6) merge 후 main에서 baseline ratchet

```bash
set -euo pipefail
cd "$(git rev-parse --show-toplevel)/webcore_appcore_starter_4_17"

git checkout main
git pull --ff-only

bash scripts/ops/prove_update_retriever_baseline.sh --update-baseline --min-gain 0.001
```

**주의 (정본):**
- Step4-B B에서는 `--reanchor-input` 사용 금지입니다.
- 입력 고정 상태이므로 re-anchoring 불필요

---

## 운영 서버 접속 규칙 (고정)

```
ssh -o StrictHostKeyChecking=no <USER>@49.50.139.248
```

---

## 참고 문서

- PR 본문 정본: `docs/ops/R10S7_STEP4B_B_PR_BODY.md`
- PR 템플릿: `docs/ops/R10S7_STEP4B_B_PR_TEMPLATE.md`
- Cursor 원샷 프롬프트: `docs/ops/R10S7_STEP4B_B_CURSOR_PROMPT.md`
- 로컬 원샷 실행 스크립트: `docs/ops/R10S7_STEP4B_B_ONE_SHOT_PROMPT.sh`
- PR 메타데이터 자동 생성: `docs/ops/R10S7_STEP4B_B_PR_METADATA_GEN.sh`
- PR 생성 전 체크: `docs/ops/R10S7_STEP4B_B_PR_PREFLIGHT_CHECK.sh`

