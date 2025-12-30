# [S7 Step4-B B] PR 메타데이터 자동 생성/Preflight 가드 봉인 완료 (CLOSED & SEALED)

**봉인일**: 2025-12-30  
**상태**: CLOSED & SEALED

---

## 봉인 완료 항목

### 1. PR 메타데이터 자동 생성

- **스크립트**: `docs/ops/R10S7_STEP4B_B_PR_METADATA_GEN.sh`
- **동작**:
  - Preflight 체크 자동 실행
  - 현재 브랜치명 자동 감지
  - PR 메타데이터 (Base/Compare/Title/Body) 자동 출력
- **보호**: main 브랜치에서 실행 시 즉시 FAIL (개선 브랜치 강제)

### 2. Preflight 가드

- **스크립트**: `docs/ops/R10S7_STEP4B_B_PR_PREFLIGHT_CHECK.sh`
- **검사 항목**:
  - 입력(goldenset/corpus) 변경 0
  - baseline 변경 0
- **실행 시간**: 10초 내 결정적 검사
- **결과**: PASS일 때만 PR 생성 진행

### 3. 정본 규칙 봉인

- **`--reanchor-input` 사용 금지**
  - `--reanchor-input`는 입력 변경 A 전용
  - Step4-B B(입력 고정)에서는 사용 금지
- **merge 후 main baseline ratchet (입력 고정)**
  ```bash
  bash scripts/ops/prove_update_retriever_baseline.sh --update-baseline --min-gain 0.001
  ```
  - `--reanchor-input` 옵션 없음 (입력 고정이므로 불필요)

---

## 실행 순서 정본

전체 실행 순서는 다음 문서를 참조:
- `docs/ops/R10S7_STEP4B_B_EXECUTION_GUIDE.md`

**6단계 요약:**
1. 개선 브랜치 생성
2. 알고리즘 변경 (입력/baseline 절대 변경 금지)
3. PR 생성 전 Preflight + PR 메타 자동 출력
4. 로컬에서 "Gate PASS + Strict Improvement JSON 증빙" 생성
5. PR 생성 (Preflight 출력 그대로 사용)
6. merge 후 main에서 baseline ratchet

---

## 성공 기준 (정본)

- Regression Gate PASS
- Strict improvement ≥ 1 (JSON 정본 증빙)
- meta-only PASS + proof/.latest + META_ONLY_DEBUG 유지

---

## 운영 서버 접속 규칙 (고정)

```
ssh -o StrictHostKeyChecking=no <USER>@49.50.139.248
```

---

## 다음 단계

이제 남은 것은 **Step4-B B "실제 알고리즘 개선 PR"**을 한 번 완주하여,
다음 6단계를 증빙(proof/.latest + META_ONLY_DEBUG)으로 닫는 것입니다:

1. Preflight PASS
2. Regression Gate PASS
3. strict improvement JSON
4. CI PASS
5. merge
6. main ratchet

**주의**: 브랜치명을 주지 않아도 Preflight가 이미 Compare(브랜치명)까지 자동 출력하도록 봉인되어 있으니, 그 출력 그대로 PR을 생성하시면 됩니다.

---

**봉인 완료**: S7 Step4-B B PR 메타데이터 자동 생성 및 Preflight 가드는 모든 하드 게이트를 통과하고, 정본 규칙으로 봉인되었습니다.

