# S7 Step4-B A — Data Expansion 절차 봉인 완료 (CLOSED & SEALED)

**종결일**: 2025-12-30  
**상태**: CLOSED & SEALED

## CI 분기/차단 봉인

### 입력 변경 PR 분기
- **입력 변경 PR**: `input_changed=1`일 때 Data Expansion Gate만 실행, Regression Gate는 Skipped
- **혼합 PR(input+algo)**: 즉시 FAIL
- **baseline 변경 PR**: 즉시 FAIL
- **실증**: 실증 PR 2개로 FAIL 확인 후 폐기/브랜치 삭제 완료

### CI 워크플로우 스텝
- `Detect S7 input changes`: `input_changed`, `algo_changed`, `baseline_changed` 출력
- `Block mixed PR (input + algo)`: 혼합 PR 차단
- `Block baseline change in PR`: baseline 변경 차단
- `S7 Data Expansion Gate`: 입력 변경 PR에서만 실행
- `S7 Regression Gate`: 입력 변경 PR에서는 Skipped

## Data Expansion PR 하드 게이트 충족

- ✅ **Always On PASS**
- ✅ **corpus PII gate PASS**
- ✅ **meta-only PASS** + proof에 META_ONLY_DEBUG scan/exclude 증거 포함
- ✅ **Phase1 report 생성 PASS** (meta-only)
- ✅ **proof/.latest 갱신 PASS**

### 증빙 파일
- `docs/ops/r10-s7-step4-data-expansion-proof-20251229-112127.log`
- `docs/ops/r10-s7-step4-data-expansion-proof.latest`
- META_ONLY_DEBUG 섹션 포함 확인

## main re-anchoring 봉인 완료

### 입력 해시 변경 시 baseline re-anchoring 절차
입력 해시 변경에 대해 main에서 명시 승인 절차로 baseline re-anchoring 수행:

```bash
bash scripts/ops/prove_update_retriever_baseline.sh --update-baseline --min-gain 0.00 --reanchor-input
```

**주의사항**:
- `--reanchor-input` 옵션은 **main 브랜치에서만 허용**됨
- non-main 브랜치에서 사용 시 즉시 FAIL
- 입력 해시 불일치 시 기본 동작은 FAIL (명시 승인 필요)
- re-anchoring은 merge 후 main에서만 수행

### re-anchoring 완료 증빙
- ✅ baseline proof log/.latest 생성 및 커밋/푸시 완료
- ✅ re-anchoring 이후 `bash scripts/ops/verify_retriever_regression_gate.sh` PASS 복귀 확인
- ✅ meta-only PASS 유지

## 최종 상태

1. **S7 Step4-B A 절차는 문서 및 proof/.latest, META_ONLY_DEBUG 증거로 레포에 영구 봉인됨**
   - 본 문서: `docs/ops/R10S7_STEP4B_A_DATA_EXPANSION_CLOSEOUT.md`
   - Proof log: `docs/ops/r10-s7-step4-data-expansion-proof-*.log`
   - Latest pointer: `docs/ops/r10-s7-step4-data-expansion-proof.latest`

2. **입력 변경 PR이 회귀 게이트를 우회하는 경로는 구조적으로 차단됨**
   - CI 워크플로우에서 `input_changed=1`일 때 Regression Gate는 Skipped
   - 입력 변경 PR에서는 baseline 비교를 수행하지 않음 (입력 해시 불일치)

3. **입력 해시 변경 시 baseline re-anchoring은 명시 승인 절차로만 허용됨**
   - 기본 동작은 입력 해시 불일치 시 FAIL (안전성 유지)
   - merge 후 main에서 re-anchoring 수행

## 다음 단계

**Step4-B B (입력 고정 알고리즘 개선 PR)**로 strict improvement를 Regression Gate PASS 하에서 달성하고, merge 후 main에서 ratchet로 baseline 상향을 수행하는 흐름으로 진행한다.

### 정본 분리 원칙

1. **입력 변경 PR에서는 기존 baseline과의 Regression Gate PASS 기대를 금지하며, merge 후 main에서 re-anchoring 이후에만 baseline 비교가 유효하다.**

2. **알고리즘 개선 PR은 입력 고정(변경 0) 상태에서만 Regression Gate PASS + strict improvement 증빙으로 운영한다.**

## 운영 서버 접속 코드 (고정)

```
ssh -o StrictHostKeyChecking=no <USER>@49.50.139.248
```

## 참고: CI 검증 가이드

상세한 CI 로그 확인 방법 및 실증 절차는 다음 문서를 참조:
- `docs/ops/S7_STEP4_B_CI_VERIFICATION_GUIDE.md`

---

**봉인 완료**: S7 Step4-B A Data Expansion 절차는 모든 하드 게이트를 통과하고, CI 분기/차단이 구조적으로 봉인되었으며, main re-anchoring 절차가 명시 승인으로 고정되었습니다.
