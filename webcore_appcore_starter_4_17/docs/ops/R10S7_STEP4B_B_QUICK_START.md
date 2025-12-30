# S7 Step4-B B 즉시 실행 가이드 (정본)

## SSOT 기준 문서 (2개)

실제 Step4-B B 알고리즘 개선 PR은 다음 2개 문서만 기준으로 진행:

1. **`docs/ops/R10S7_STEP4B_B_EXECUTION_GUIDE.md`** - 실행 순서 정본
2. **`docs/ops/R10S7_STEP4B_B_ANNOUNCEMENT.md`** - 검토팀/개발팀 공지

---

## 핵심 실행 흐름 (정본)

### 1. 개선 브랜치에서 Preflight + PR 메타데이터 출력

```bash
bash docs/ops/R10S7_STEP4B_B_PR_METADATA_GEN.sh
```

**출력:**
- Preflight PASS 확인
- PR 메타데이터 (Base/Compare/Title/Body) 자동 출력

**주의:**
- main 브랜치에서 실행 시 즉시 FAIL (개선 브랜치 강제)
- Preflight 출력 그대로 PR 생성 (복붙 실수 제거)

### 2. 로컬/CI에서 Regression Gate PASS + strict improvement JSON 증빙

```bash
bash docs/ops/R10S7_STEP4B_B_ONE_SHOT_PROMPT.sh
```

**성공 기준:**
- Regression Gate PASS
- Strict improvement ≥ 1 (JSON 정본 증빙)
- meta-only PASS + proof/.latest + META_ONLY_DEBUG 유지

### 3. PR 생성/머지

- Preflight가 출력한 Base/Compare/Title/Body를 그대로 사용
- CI에서 Regression Gate 필수 실행 + PASS 확인

### 4. 머지 후 main에서 ratchet

```bash
bash scripts/ops/prove_update_retriever_baseline.sh --update-baseline --min-gain 0.001
```

**정본 규칙:**
- Step4-B B에서는 `--reanchor-input` 사용 금지
- 입력 고정 상태이므로 re-anchoring 불필요

---

## zsh 주석 오염 재발 방지 (정본)

주석(# ...)이 섞인 멀티라인 블록을 zsh에 그대로 붙여넣을 때 오염이 반복될 수 있으므로, 아래 둘 중 하나로 고정:

### 방법 A: 어떤 쉘에서도 bash로 강제 실행

```bash
bash -lc '
set -euo pipefail
# 여기에는 주석이 있어도 bash가 정상 처리합니다
echo OK
'
```

### 방법 B: 스크립트 파일로 저장 후 bash로 실행

```bash
cat > /tmp/run_step4b_b.sh <<'SH'
set -euo pipefail
# 주석 포함 가능
echo OK
SH
bash /tmp/run_step4b_b.sh
```

---

## 운영 서버 접속 규칙 (고정)

```
ssh -o StrictHostKeyChecking=no <USER>@49.50.139.248
```

---

## 참고

- 브랜치명을 주지 않아도 Preflight가 PR 메타데이터(Base/Compare/Title/Body)를 자동 출력하도록 봉인되어 있으니, 개발팀은 Preflight 출력 그대로 PR을 생성하시면 됩니다.

