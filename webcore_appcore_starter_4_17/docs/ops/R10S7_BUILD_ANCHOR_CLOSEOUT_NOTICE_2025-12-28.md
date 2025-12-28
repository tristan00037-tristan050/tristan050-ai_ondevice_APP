# [Closeout Notice] R10-S7 Build Anchor 사고 — 종결(CLOSED) 정본 v1.1-r1 (2025-12-28)

## [종결 보고] R10-S7 Build Anchor 사고 Post-Mortem 발행 및 재발 0 잠금 종결(CLOSED)

### 1) 최종 상태
- 상태: **CLOSED**

#### 결정적 근거(증빙)
- CI Hard Gate 통과  
  - main 최신 GitHub Actions run에서 build/e2e job 기준 verify + destructive 모두 PASS(하드 게이트 통과).
- 로컬 원샷 증빙 로그 완주  
  - docs/ops/r10-s7-one_shot_proof_20251228-044642.log  
  - 로그 내 단계: BUILD → START BFF → VERIFY → DESTRUCTIVE → PROVE_FAST → END  
  - destructive가 "변조 후 FAIL(exit=1) → 원복 후 PASS" 절차 완주(파괴 테스트 결정성 실증).
- proof 및 .latest 포인터 정합성  
  - proof: docs/ops/r10-s7-build-anchor-esm-proof-20251228-044649.log  
  - latest: docs/ops/r10-s7-build-anchor-esm-proof.latest → r10-s7-build-anchor-esm-proof-20251228-044649.log
- Post-Mortem 영구 보존(레포 정본)  
  - Post-Mortem: docs/R10S7_BUILD_ANCHOR_POST_MORTEM.md  
  - Post-Mortem 커밋(패치로 확인됨):  
    - Commit: 840f70685ea0e1a810403f349c4e88a0be86cdf5  
    - Message: docs(ops): add post-mortem report for R10-S7 build anchor incident
- Closeout Notice(운영 종결 고정 문서)  
  - Closeout Notice: docs/ops/R10S7_BUILD_ANCHOR_CLOSEOUT_NOTICE_2025-12-28.md  
  - 포함 항목(문서 본문 기준): Final Status(CLOSED), Golden Proofs, Permanent Post-Mortem Record, Dev Team Hard Rules(No Mixing), Zero Tolerance  
  - (존재/내용은 아래 "커밋/경로 사실 확인 커맨드"로 즉시 재검증)

---

### 2) 사고/오류 목록(사실 기반)과 구조적 해결(요약)

#### build anchor unknown 생존
- 증상: /healthz에서 Header/JSON이 unknown, ESM 로딩 실패 흔적
- 원인: ESM 환경에서 require/경로 해석 실패 시 로드 실패가 fail-open로 남을 수 있었음
- 해결: build_info 생성/검증을 스크립트 + CI 하드 게이트로 승격, /healthz 무결성(헤더/JSON/HEAD 일치) 강제

#### verify 오판(000/빈 문자열)
- 증상: BFF는 살아있는데 verify가 000/빈 문자열로 FAIL
- 원인: 상태코드 추출이 실패 케이스에서 비거나 출력이 섞일 수 있는 구조
- 해결: curl -sS -o /dev/null -w "%{http_code}" 기반 fail-safe + 재시도 + 진단 출력 고정

#### destructive 결정성 붕괴(빌드 덮어쓰기)
- 증상: 변조 후 재기동 시 빌드가 다시 돌아 변조가 덮여 FAIL 재현 불가
- 원인: restart 과정에서 workspace build 재실행 + build_info 재생성
- 해결: DEV_BFF_SKIP_BUILD=1로 덮어쓰기 차단, 변조 후 FAIL → 원복 후 PASS 절차를 결정적으로 고정

#### Cursor run hang(포그라운드 dev 점유)
- 증상: dev_bff restart에서 다음 단계로 진행 불가
- 원인: dev 서버가 포그라운드로 스크립트를 붙잡음
- 해결: dev_bff를 종료형(백그라운드+PID)으로 전환, follow는 opt-in, MAX_WAIT=10 시간 상한 고정

#### zsh/VSCode 훅 오염
- 증상: 파싱 에러/제어문자 유입 등으로 실행 깨짐
- 원인: zsh 설정/붙여넣기 모드 영향
- 해결: 검증/증빙은 ops 스크립트 또는 bash -lc로만 수행

---

### 3) 검토팀 하드룰(검토 실수 감소)
#### PASS 선언 금지 조건(모두 충족 필요)
- CI Hard Gate(build/e2e) verify+destructive PASS 증빙
- One-Shot Proof 로그(END 포함)
- proof 및 .latest 정합성(최신 proof 존재)

#### 운영 원칙
- "요약문" 신뢰 금지: 위 3개 증거로만 판정
- destructive 절차 미완주 상태는 즉시 차단
- 스크립트 종료형 유지 여부(dev_bff가 포그라운드 점유하지 않는지) 필수 점검

---

### 4) 개발팀 하드룰(실수 감소, 혼용 금지)
- 표준 커맨드 3종만 사용  
  - verify: BASE_URL="http://127.0.0.1:8081" bash scripts/ops/verify_build_anchor.sh  
  - destructive: bash scripts/ops/destructive_build_anchor_should_fail.sh  
  - prove(정식): bash scripts/ops/prove_build_anchor.sh
- 반복 루프(결정성/속도)  
  - 덮어쓰기 방지 재기동: DEV_BFF_SKIP_BUILD=1 ./scripts/dev_bff.sh restart  
  - 속도 증빙: PROVE_FAST=1 bash scripts/ops/prove_build_anchor.sh
- Ctrl+C 중단 실행은 증빙 0
- CI Hard Gate 우회 금지: CI FAIL이면 미완료

---

### 5) 추가: "커밋/경로 사실 확인"용 로컬 커맨드(검토팀/개발팀 공통)
아래 커맨드로 문서/증빙 파일이 실제 main(HEAD)에 존재하는지 즉시 확인합니다.

```bash
set -euo pipefail
cd "$(git rev-parse --show-toplevel)/webcore_appcore_starter_4_17"

# 1) 경로 존재 확인(HEAD 기준)
git ls-tree -r --name-only HEAD | rg \
"docs/R10S7_BUILD_ANCHOR_POST_MORTEM\.md|docs/ops/R10S7_BUILD_ANCHOR_CLOSEOUT_NOTICE_2025-12-28\.md|docs/ops/r10-s7-one_shot_proof_20251228-044642\.log|docs/ops/r10-s7-build-anchor-esm-proof-20251228-044649\.log|docs/ops/r10-s7-build-anchor-esm-proof\.latest"

# 2) .latest 포인터 정합성(내용/대상 파일 존재)
cat docs/ops/r10-s7-build-anchor-esm-proof.latest
PROOF="$(cat docs/ops/r10-s7-build-anchor-esm-proof.latest | tr -d "\r\n")"
test -f "docs/ops/$PROOF"

# 3) Post-Mortem 커밋 존재/메시지 확인
git show -s --format="%H %s" 840f70685ea0e1a810403f349c4e88a0be86cdf5

# 4) 원샷 로그 단계 존재 확인(결정적)
rg -n "== BUILD|== START BFF|== VERIFY|== DESTRUCTIVE|== PROVE_FAST|ONE_SHOT_DONE|== END" \
docs/ops/r10-s7-one_shot_proof_20251228-044642.log
```
