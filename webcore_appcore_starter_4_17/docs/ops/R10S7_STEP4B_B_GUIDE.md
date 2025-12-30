# S7 Step4-B B (입력 고정 알고리즘 개선 PR) 가이드

## 성공 정의 (4개 동시 만족)

### 하드 게이트 (merge 조건)

1. **입력 변경 0**
   - goldenset/corpus 변경 0 (CI 분기/차단 규칙으로 통제)

2. **Regression Gate PASS**
   - baseline 대비 하락 없음

3. **strict improvement ≥ 1**
   - 최소 1개 지표가 baseline보다 strictly greater

4. **Always On / meta-only / 증빙 유지**
   - proof/.latest 갱신 + proof 내 META_ONLY_DEBUG 증거 유지

## 금지 (정본)

- ❌ 입력 변경 + 알고리즘 변경 혼합 PR 금지
- ❌ PR에서 baseline 파일 변경 금지 (0)
- ❌ FAIL을 "정상"으로 기록 금지
- ❌ META_ONLY_DEBUG 증거 없이 PASS 선언 금지 (요약 금지, proof가 증거)

## 원샷 로컬 체크 블록 (PR 만들기 직전 1분 점검)

```bash
bash -lc '
set -euo pipefail
cd "$(git rev-parse --show-toplevel)/webcore_appcore_starter_4_17"

# Always On
bash scripts/ops/verify_s7_always_on.sh

# 입력 고정(변경 0) 강제 확인
git fetch origin main --depth=1
CHANGED="$(git diff --name-only origin/main...HEAD)"
echo "$CHANGED" | sed -n "1,200p"

echo "$CHANGED" | rg -n "docs/ops/r10-s7-retriever-(goldenset\.jsonl|corpus\.jsonl)" && {
  echo "FAIL: input must be frozen for Step4-B B"
  exit 1
} || true

echo "$CHANGED" | rg -n "docs/ops/r10-s7-retriever-metrics-baseline\.json" && {
  echo "FAIL: baseline must not be modified in PR"
  exit 1
} || true

# Safety gates (meta-only)
bash scripts/ops/verify_s7_corpus_no_pii.sh

# Regression proof (must PASS)
bash scripts/ops/prove_retriever_regression_gate.sh

# Meta-only scan + debug evidence
META_ONLY_DEBUG=1 bash scripts/ops/verify_rag_meta_only.sh

# Strict improvement check (meta-only metrics only)
python3 - <<PY
import json
b=json.load(open("docs/ops/r10-s7-retriever-metrics-baseline.json","r",encoding="utf-8"))
r=json.load(open("docs/ops/r10-s7-retriever-quality-phase1-report.json","r",encoding="utf-8"))
keys=["precision_at_k","recall_at_k","mrr_at_k","ndcg_at_k"]
improved=[]
print("=== STRICT IMPROVEMENT CHECK (meta-only) ===")
out={"improved_keys":[], "metrics":{}}
for k in keys:
    bv=float(b["metrics"][k]); rv=float(r["metrics"][k])
    out["metrics"][k]={"baseline":round(bv,6),"current":round(rv,6),"delta":round(rv-bv,6)}
    if rv>bv: improved.append(k)
out["improved_keys"]=improved
print(json.dumps(out, ensure_ascii=False, indent=2))
raise SystemExit(0 if improved else 1)
PY
'
```

## merge 후 main에서 baseline 상향 (ratchet)

Step4-B B는 **입력 고정 상태의 "성능 개선"**이므로, merge 후 main에서 re-anchoring이 아니라 ratchet로 올립니다.

**`--reanchor-input`는 입력 변경 A 전용이며, Step4-B B(입력 고정)에서는 사용하지 않습니다.**

```bash
# main에서만
bash scripts/ops/prove_update_retriever_baseline.sh --update-baseline --min-gain 0.001
```

**주의사항**:
- `--min-gain`은 팀 기준값으로 운용 (예: 0.001 또는 0.005 등)
- 입력 해시가 동일하므로 `--reanchor-input` 옵션 불필요

## 운영 서버 접속 코드 (고정)

```
ssh -o StrictHostKeyChecking=no <USER>@49.50.139.248
```

## 참고 문서

- **실행 순서 정본**: `docs/ops/R10S7_STEP4B_B_EXECUTION_GUIDE.md`
- **검토팀/개발팀 공지**: `docs/ops/R10S7_STEP4B_B_ANNOUNCEMENT.md`
- PR 템플릿: `docs/ops/R10S7_STEP4B_B_PR_TEMPLATE.md`
- PR 본문 정본: `docs/ops/R10S7_STEP4B_B_PR_BODY.md`
- PR 메타데이터 자동 생성: `docs/ops/R10S7_STEP4B_B_PR_METADATA_GEN.sh`
- PR 생성 전 체크: `docs/ops/R10S7_STEP4B_B_PR_PREFLIGHT_CHECK.sh`
- Cursor 원샷 프롬프트: `docs/ops/R10S7_STEP4B_B_CURSOR_PROMPT.md`
- 로컬 원샷 실행 스크립트: `docs/ops/R10S7_STEP4B_B_ONE_SHOT_PROMPT.sh`
- 개발팀 실행 템플릿: `docs/ops/R10S7_DEVELOPER_EXECUTION_TEMPLATE.md`

