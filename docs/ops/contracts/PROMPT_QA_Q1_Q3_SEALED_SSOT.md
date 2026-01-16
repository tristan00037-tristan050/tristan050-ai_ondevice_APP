# Prompt QA 강제 체계(Q1~Q3) 운영 종결(SEALED) — SSOT

Prompt-Version: 1.0
Owner: Platform Team
Last-Reviewed: 2026-01-16

## Problem
Prompt/Rule/Contract 변경 품질이 사람 기억에 의존하면 기준이 흔들리고 재발 경로가 열립니다.
따라서 Prompt QA를 “권고”가 아니라 “머지 차단(merge-blocking)”으로 고정합니다.

## Scope
### MUST include
- Prompt QA(Q1~Q3) 운영 종결(SEALED): prompt-lint 게이트 + required checks + CODEOWNERS + 품질 계약(PROMPT_QUALITY_BAR_V1) 봉인
- SSOT 경로 변경이 “prompt-lint PASS + Code Owner 승인” 없이는 main 머지 불가인 구조
- required check 운영 함정 2개(Expected/Waiting vs skipped)와 방지 문장(스킵 우회 차단)
- 후속 PR #107/#108은 “merged 입력”만 반영하고, 범위/DoD 키는 PR Files changed + checks(출력)로 meta-only 확정 후 편입

### MUST NOT include
- 명칭/이름/코드명 논의(본 SSOT 범위 밖)

## Invariants
- Output-based only (말로 PASS 금지, 기록/출력으로만 판정)
- meta-only (원문/덤프/대량 인용 금지)
- Fail-Closed (애매하면 막고, reason_code를 남긴다)
- 1 PR = 1 Purpose

## DoD
- 보호 브랜치(main)에서 required check(prompt-lint)가 PASS가 아니면 머지 불가
- SSOT 경로 변경 시 CODEOWNERS 승인 없으면 머지 불가
- 품질 계약(PROMPT_QUALITY_BAR_V1)이 main에 봉인되어 기준이 흔들리지 않음

## Failure Modes (FMEA) & Threat Model
- FM1: required check 상태가 “보고되지 않음” → PR이 Waiting/Expected로 멈춤
  - Control: 모든 PR에서 required check 상태가 항상 보고되도록 유지 (Q1 보완 #105 정렬)
  - reason_code=PQA_EXPECTED_WAITING
- FM2: 워크플로는 떴지만 required job/step이 조건식으로 skipped → 성공으로 취급될 수 있어 차단 약화
  - Control: required check job/step은 조건식으로 쉽게 skipped 되지 않도록 유지
  - reason_code=PQA_SKIPPED_BYPASS
- FM3: required check 선택 시 “표기 이름(체크 런/잡)” 혼선 → 잘못된 체크를 required로 걸어 무력화/오판 위험
  - Control: Required status check는 GitHub UI에 표시되는 체크 런(보통 job) 이름 기준으로 고정, job 이름은 유니크하게 유지
  - reason_code=PQA_CHECKNAME_MISMATCH
- FM4: CODEOWNERS 미적용(위치/우선순위/베이스 브랜치 조건 불충족) → 리뷰 강제 누락
  - Control: CODEOWNERS는 base 브랜치(main)에 존재해야 하며, .github/ → root → docs/ 우선순위를 준수
  - reason_code=PQA_CODEOWNERS_NOT_APPLIED

## Reason Codes
- PQA_EXPECTED_WAITING
- PQA_SKIPPED_BYPASS
- PQA_CHECKNAME_MISMATCH
- PQA_CODEOWNERS_NOT_APPLIED

## Rollback
- 필요한 경우: 관련 PR revert로 되돌린다.
- 영향 범위는 SSOT 경로와 CI/보호 규칙에 한정하며, 1 PR=1 목적을 유지한다.

## References
- Internal SSOT inputs (user-provided):
  - PR #102 merged (prompt-lint gate)
  - PR #105 merged (prompt-lint status always reported on PRs)
  - PR #104 merged (CODEOWNERS wired to real accounts for SSOT paths)
  - PR #106 merged (PROMPT_QUALITY_BAR_V1 sealed)
  - PR #107 merged (follow-up; scope/DoD to be confirmed via Files changed + checks)
  - PR #108 merged (follow-up; scope/DoD to be confirmed via Files changed + checks)
- GitHub Docs (external behavior):
  - Required status checks (success/skipped/neutral; waiting-for-status; skipped semantics)
  - Code owners (locations/precedence; base branch requirement)
  - Protected branches / rulesets (require code owner reviews; required checks)
