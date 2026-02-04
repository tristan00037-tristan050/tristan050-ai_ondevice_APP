# [Post-Mortem] R10-S7 ESM Build Anchor Incident (Fixed & Locked)

## 1. Summary
- **Status:** **CLOSED (Fixed & Recurrence Locked)**
- **Date:** 2025-12-28
- **Scope:** Build Anchor "Fail-Closed Architecture" + Deterministic Verify/Destructive + CI Hard Gate
- **Final Verdict (Test/Remediation Team):** **PASS (재발 0 잠금 완료, 운영 종결)**

### Golden Proofs (Deterministic Evidence)
- **CI Hard Gate (main 최신 run, build/e2e job):** verify + destructive **모두 PASS 확인됨**
- **One-Shot Proof Log (완주):** `docs/ops/r10-s7-one_shot_proof_20251228-044642.log`  
  - Coverage: **BUILD → START BFF(no hang) → VERIFY → DESTRUCTIVE(FAIL→PASS) → PROVE_FAST → END**
- **Proof Log:** `docs/ops/r10-s7-build-anchor-esm-proof-20251228-044649.log`
- **Pointer:** `docs/ops/r10-s7-build-anchor-esm-proof.latest` → `r10-s7-build-anchor-esm-proof-20251228-044649.log`

---

## 2. Root Cause & Structural Fixes (결정성/재현성 기준)

| Symptom (사실 기반) | Root Cause (원인) | Structural Fix (구조적 해결) |
|---|---|---|
| **Build Anchor가 unknown으로 살아남음** / `/healthz`에서 Header/JSON이 `"unknown"` | ESM 런타임에서 `require` 사용/경로 해석 실패로 `build_info` 로드 실패가 **fail-open**으로 남을 수 있었음 | **fail-closed 부트**로 전환(로드 실패 시 즉시 종료), `build_info` 생성/검증을 **스크립트/CI 게이트**로 승격, `/healthz` 삼각 무결성(HEAD/JSON/Header) 결정적 고정 |
| **verify가 000/빈 문자열로 오판** (BFF는 살아있는데 FAIL) | 상태코드/응답 추출 로직이 실패 케이스에서 값이 비거나 바디와 섞일 수 있는 구조 | `curl -sS -o /dev/null -w "%{http_code}"` 기반 **fail-safe**, 재시도, 실패 시 진단 출력(LISTEN/verbose curl/log tail)로 원인 추적 시간을 제거 |
| **destructive가 결정적 FAIL을 만들지 못함** (변조가 덮여써져 FAIL 미재현) | `dev_bff.sh restart`가 dist freshness 판정으로 workspace build를 재실행하며 `generate_build_info`가 변조를 **재생성/덮어쓰기** | `DEV_BFF_SKIP_BUILD=1` 도입으로 재기동 시 빌드/덮어쓰기 차단, destructive를 **"변조 후 FAIL(exit=1) → 원복 후 PASS"**로 절차 고정 |
| **Cursor/원샷 루프가 멈춘 것처럼 보임** | `dev_bff.sh restart`가 `npm run dev:bff`를 포그라운드로 붙잡아 스크립트가 종료되지 않음 | `dev_bff.sh`를 **종료형**으로 전환(nohup 백그라운드 + PID 기록, wait 제거), 기본은 즉시 exit 0, `DEV_BFF_FOLLOW_LOG=1`일 때만 follow 허용, `MAX_WAIT=10`으로 시간 통제 |
| **zsh/VSCode 훅 오염** (parse error, 제어문자 유입 등) | zsh strict/bracketed paste/훅 환경에서 블록 복붙이 오염됨 | 검증/증빙은 **ops 스크립트 실행 또는 bash -lc**로만 수행하도록 운영 표준 고정 |

---

## 3. Deterministic Verification Contract (검증 계약)
본 잠금은 "이번에 PASS"가 아니라 **사람 실수로는 흔들릴 수 없는 계약**을 구현한다.

### 3.1 Triangulation (삼각 무결성)
- **Git HEAD == /healthz JSON buildSha == /healthz Header X-OS-Build-SHA**
- unknown/빈값/40-hex 미만은 **절대 통과 불가(fail-closed)**

### 3.2 Verify Script Determinism
- FAIL을 한 번이라도 출력하면 즉시 `exit 1`
- 네트워크/기동 순간차에 의한 false fail을 제거하기 위해:
  - http_code는 `%{http_code}`로 결정적으로 추출
  - 재시도 + 실패 진단 출력으로 "원인 추적 시간"을 구조적으로 제거

---

## 4. Deterministic Destructive Test Rule (파괴 테스트 정본)
**확률적 실패는 버그다. 결정적 실패만이 테스트다.**

### Required Procedure (항상 동일)
1) **Mutation 주입:** build_info를 변조(테스트 정의에 따라 1개 방식으로 고정)  
2) **BFF 재기동:** 변조가 런타임에 반영되게 함  
   - 이때 **빌드 덮어쓰기 금지:** `DEV_BFF_SKIP_BUILD=1`  
3) **Wait Loop:** healthz 안정 응답까지 대기(상한 포함)  
4) **Verify:** 기대 결과는 **항상 FAIL(exit!=0)**  
5) **Restore:** 원복 후 재기동 → verify는 **항상 PASS**로 복귀

---

## 5. Operational Standard (SOP / Hard Rules)
개발 실수의 대부분은 "로컬에서는 됨"과 "CI/운영 재현"의 간극에서 발생한다. 아래 5개는 혼용 금지.

### R-DEV-1: 표준 커맨드 3종(혼용 금지)
- **증빙(최종 종결):**
  ```bash
  cd "$(git rev-parse --show-toplevel)/webcore_appcore_starter_4_17"
  bash scripts/ops/prove_build_anchor.sh
  ```
- **검증(떠 있는 BFF 검증):**
  ```bash
  BASE_URL="http://127.0.0.1:8081" bash scripts/ops/verify_build_anchor.sh
  ```
- **파괴 테스트(결정적 FAIL→PASS):**
  ```bash
  bash scripts/ops/destructive_build_anchor_should_fail.sh
  ```

### R-DEV-2: 스크립트 종료형 원칙
- `dev_bff.sh restart`는 기본적으로 반드시 종료(exit 0)
- 로그 follow는 `DEV_BFF_FOLLOW_LOG=1`에서만 허용

### R-DEV-3: 반복 루프 속도/안정성 하드룰
- **반복 검증(덮어쓰기 방지):**
  ```bash
  DEV_BFF_SKIP_BUILD=1 ./scripts/dev_bff.sh restart
  ```
- **반복 증빙(속도용):**
  ```bash
  PROVE_FAST=1 bash scripts/ops/prove_build_anchor.sh
  ```
- **최종 종결(정식):**
  ```bash
  bash scripts/ops/prove_build_anchor.sh
  ```

### R-DEV-4: "취소된 Run"은 결과로 기록 금지
- Ctrl+C로 중간 취소된 실행은 증빙 0
- PASS는 반드시 one-shot proof log(END 포함) 또는 proof log/.latest로 남아야 함

### R-DEV-5: CI Hard Gate 우회 금지
- verify + destructive는 CI build/e2e job에서 필수 PASS
- 로컬 PASS라도 CI FAIL이면 작업은 미완료

---

## 6. Closing Statement
본 건은 로컬 one-shot 증빙 로그, proof/.latest 포인터, 그리고 main CI Hard Gate PASS로 결정적으로 실증 완료되었다.
검증/파괴/증빙 절차는 ops 스크립트 3종과 CI 게이트로 고정되어, 사람 실수로 동일 유형 장애가 재발할 가능성은 구조적으로 차단되었다.

## Appendix: Permanent Record (Verified by Commit Patch)
- **Post-Mortem Commit**
  - Message: `docs(ops): add post-mortem report for R10-S7 build anchor incident`
  - SHA: `840f70685ea0e1a810403f349c4e88a0be86cdf5`
  - Added File: `docs/R10S7_BUILD_ANCHOR_POST_MORTEM.md`

- **Golden Proofs**
  - One-Shot Proof: `docs/ops/r10-s7-one_shot_proof_20251228-044642.log`
  - Proof Log: `docs/ops/r10-s7-build-anchor-esm-proof-20251228-044649.log`
  - Latest Pointer: `docs/ops/r10-s7-build-anchor-esm-proof.latest` → `r10-s7-build-anchor-esm-proof-20251228-044649.log`
