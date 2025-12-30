# R10S7 Step4-B (B) Developer Quick Start (정본)

## 목표
- Step4-B B의 PR 생성/로컬 증빙/CI 통과/머지 후 ratchet까지 "실수 0"으로 실행한다.
- strict improvement 증거 파일 위치를 SSOT로 고정한다.

## 3단계 실행 순서(초간단)

### 1) 개선 브랜치에서 PR 메타데이터 자동 생성

```bash
bash docs/ops/R10S7_STEP4B_B_PR_METADATA_GEN.sh
```

**동작:**
- main에서 실행: FAIL (개선 브랜치 강제)
- 개선 브랜치에서: PASS + Base/Compare/Title/Body 완성형 출력
- 출력된 메타데이터 그대로 PR 생성(복붙 실수 제거)

### 2) 로컬 증빙(정본)

```bash
bash docs/ops/R10S7_STEP4B_B_ONE_SHOT_PROMPT.sh
```

**필수 결과:**
- Regression Gate: PASS
- strict improvement JSON(SSOT 고정 경로) 생성:
  - `docs/ops/r10-s7-step4b-b-strict-improvement.json`
- proof/.latest 생성 + META_ONLY_DEBUG 로그 포함

### 3) CI PASS 후 merge → merge 후 main ratchet

```bash
bash scripts/ops/prove_update_retriever_baseline.sh --update-baseline --min-gain 0.001
```

**정본 규칙:**
- Step4-B B에서는 `--reanchor-input` 사용 금지(A 전용)

---

## 보강 사항(증거 위치 고정)

### strict improvement JSON SSOT 경로

- **고정 경로**: `docs/ops/r10-s7-step4b-b-strict-improvement.json`
- JSON은 meta-only 준수(메트릭 키/숫자만 포함)
- 텍스트/PII/시크릿/쿼리 원문/문서 원문 포함 금지

---

## zsh 주석/따옴표 오염 방지(필수)

긴 블록은 반드시 아래 형태로 실행한다:

```bash
bash -lc '
set -euo pipefail
# ... commands ...
'
```

**주의:**
- heredoc(`<<'PY'`)는 시작~종료(`PY`)까지 한 덩어리로 붙여넣는다.
- 붙여넣기 중 따옴표가 깨지면 zsh이 글롭으로 해석해 실패할 수 있다.

---

## 운영 서버 접속 규칙(프로젝트 SSOT 준수)

- 운영 서버 점검/검증이 필요할 때는 "SSH 주소 + 작업 경로"를 항상 명시한다.
- 값은 프로젝트 SSOT(예: OPERATIONS/DEPLOY 문서)의 HOST/PATH를 따른다.
- 로컬/CI에서 재현 가능한 증빙(log/json)을 먼저 만든 뒤 서버 작업을 수행한다.

**고정 규칙:**
```
ssh -o StrictHostKeyChecking=no <USER>@49.50.139.248
```
