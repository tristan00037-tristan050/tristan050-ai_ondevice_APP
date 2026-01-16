# Prompt QA(Q1~Q3) 운영 종결(SEALED) — SSOT (Single Source of Truth)

Prompt-Version: 1.0
Owner: Platform Team (Platform Owner + Integration Owner)
Last-Reviewed: 2026-01-16

## Problem
Prompt/Rule/Contract 문서 품질이 사람 기억과 말에 의존하면, 기준이 흔들리고 재발 경로가 열립니다.
따라서 Prompt QA를 “권고”가 아니라 “머지 차단(merge-blocking)”으로 고정합니다.

## Scope
### MUST include
- Prompt QA(Q1~Q3) 운영 종결(SEALED) 상태: prompt-lint 게이트 + required checks + CODEOWNERS + 품질 계약(PROMPT_QUALITY_BAR_V1) 봉인
- SSOT 경로 변경이 “prompt-lint PASS + Code Owner 승인” 없이는 main 머지 불가인 구조
- required check 운영 함정 2개(Waiting/Expected vs skipped)를 분리하고, 방지 문장을 운영 표준으로 고정
- 후속 PR #107/#108은 “merged 입력”은 반영하되, 변경 범위/DoD 키는 PR의 Files changed + checks(출력)로 meta-only 확정 후 편입

### MUST NOT include
- 명칭/이름/코드명 논의(본 문서 범위 밖)
- 원문/라인 덤프/로그 전문(본 SSOT는 meta-only)

## Invariants
- Output-based only: 말로 PASS 금지. 체크/출력/기록으로만 판정
- meta-only: 본문/라인/로그 전문 출력 금지
- Fail-Closed: 애매하면 막고, reason_code를 남긴다
- 1 PR = 1 Purpose: PR 목적 혼합 금지(혼합 시 분할)

## DoD
- 보호 브랜치(main)에서 required status check(prompt-lint)가 PASS가 아니면 머지 불가
- SSOT 경로 변경 시 Code Owner 승인 없으면 머지 불가
- 품질 계약(PROMPT_QUALITY_BAR_V1)이 main에 봉인되어 기준이 흔들리지 않음
- SSOT 정본 문서는 본 파일 1개로 참조(복사본 확산 방지)

## Failure Modes / FMEA (운영 함정 2개 분리 고정)
- FM1: required check 상태가 “보고되지 않음” → PR이 Waiting/Expected(“status to be reported”)로 멈춤
  - Impact: 머지 버튼이 영구 차단될 수 있음
  - Control: 모든 PR에서 required check 상태가 항상 보고되도록 워크플로를 설계/유지
  - reason_code=PQA_EXPECTED_WAITING

- FM2: 워크플로는 떴지만 required job/step이 조건식으로 skipped → 성공으로 보고되어 차단이 약해질 수 있음
  - Impact: “required인데도 우회” 형태의 품질 저하 가능
  - Control: required check에 해당하는 job/step은 조건식으로 쉽게 skipped 되지 않도록 유지
  - reason_code=PQA_SKIPPED_BYPASS

- FM3: required check “이름(체크 런/잡)” 혼선 → 잘못된 항목을 required로 걸어 무력화/오판 위험
  - Control: Required status check는 GitHub UI에 표시되는 체크 런/잡 이름 기준으로 고정하고, job 이름을 유니크하게 유지
  - reason_code=PQA_CHECKNAME_MISMATCH

- FM4: CODEOWNERS 미적용(위치/우선순위/베이스 브랜치 조건 불충족) → 리뷰 강제 누락
  - Control: CODEOWNERS는 base 브랜치(main)에 존재해야 적용되며, .github/ → repo root → docs/ 우선순위를 준수
  - reason_code=PQA_CODEOWNERS_NOT_APPLIED

## Reason Codes
- PQA_EXPECTED_WAITING
- PQA_SKIPPED_BYPASS
- PQA_CHECKNAME_MISMATCH
- PQA_CODEOWNERS_NOT_APPLIED

## Rollback
- 필요한 경우: 관련 PR revert로 되돌린다.
- 영향 범위는 SSOT 경로 + CI/보호 규칙에 한정하며, 1 PR=1 목적을 유지한다.

## References
### Internal SSOT inputs (user-provided)
- PR #102 merged: prompt-lint 게이트 구축
- PR #105 merged: 모든 PR에서 prompt-lint 상태 보고(Waiting/Expected 함정 제거 정렬)
- PR #104 merged: CODEOWNERS 실제 계정 연결(SSOT 경로 code owner 지정)
- PR #106 merged: PROMPT_QUALITY_BAR_V1 봉인(“박사급 정의 + Gate PASS 전제”)
- PR #107 merged: 후속(범위/DoD 키는 Files changed + checks로 meta-only 확정 후 편입)
- PR #108 merged: 후속(범위/DoD 키는 Files changed + checks로 meta-only 확정 후 편입)
- PR #109 merged: 본 SSOT 문서를 단일 진실원(single source of truth)으로 봉인

### GitHub Docs (external behavior)
- About required status checks: https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-protected-branches/about-required-status-checks
- About protected branches: https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-protected-branches/about-protected-branches
- About code owners (CODEOWNERS): https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/customizing-your-repository/about-code-owners

---

# 복붙 블록 4종 (SSOT에서만 복사하여 사용)

대상 경로: .cursor/rules/**, docs/ops/cursor_prompts/**, docs/ops/contracts/**

## 6-1) 팀 내부 공지용(복붙)

제목
[SEALED] Prompt QA 강제 체계(Q1~Q3) 운영 종결 (prompt-lint + CODEOWNERS + 품질 계약 봉인)

본문
최종 결론: Prompt QA는 개인 역량이 아니라 시스템 하한선(머지 차단)으로 강제되는 체계로 종결되었습니다.

근거(SSOT 입력 기준, merged)
- Q1 Gate: PR #102 merged (prompt-lint 게이트)
- Q1 보완: PR #105 merged (모든 PR에서 prompt-lint 상태 보고; Waiting/Expected 함정 제거 정렬)
- Q2 Review 강제: PR #104 merged (CODEOWNERS 실제 계정 연결)
- Q3 계약 봉인: PR #106 merged (PROMPT_QUALITY_BAR_V1: “박사급 정의 + Gate PASS 전제”)
- 후속: PR #107 merged, PR #108 merged (범위/DoD 키는 Files changed + checks로 meta-only 확정 후 편입)
- SSOT 단일 진실원: PR #109 merged (본 SSOT 문서)

운영 표준(고정)
- Required status check: prompt-lint (PASS 아니면 머지 불가)
- SSOT 경로 변경은 prompt-lint PASS + Code Owner 승인 없으면 main 머지 불가
- required check job/step은 조건식으로 쉽게 skipped 되지 않도록 유지(우회 차단)

실무 규칙(팀 공통)
- SSOT 경로 변경 PR은 prompt-lint PASS + Code Owner 승인 전까지 main 머지 불가
- 테스트/검증용 PR은 머지 금지(확인 후 Close + 브랜치 삭제)

## 6-2) 타팀 공유용(복붙)

제목
[공지] Prompt QA Standard v1.0 운영 강제 시작 (SSOT 경로: prompt-lint 필수 통과 + Code Owner 승인)

본문
Prompt Registry(SSOT) 관련 변경은 이제 CI와 리뷰 규칙이 자동 강제되며,
prompt-lint PASS + Code Owner 승인 없이는 main에 머지되지 않습니다.

기본 위반 예(자동 차단)
- 필수 섹션 누락
- References 비어 있음
- 스탬프(Owner/Last-Reviewed 등) 누락
→ CI FAIL → 머지 차단

정본(단일 진실원)
- 공지/인수인계/감사는 레포의 SSOT 파일(PROMPT_QA_Q1_Q3_SEALED_SSOT.md)만 참조합니다(복사본 확산 금지).

## 6-3) 알고리즘팀 안내용(R2 준수, 복붙)

제목
[R2 준수] 알고리즘 프롬프트는 References 근거 포함 필수 (prompt-lint 자동 검증)

본문
알고리즘 관련 프롬프트/규칙 문서도 SSOT 경로 변경으로 분류되며,
prompt-lint PASS가 아니면 main 머지 불가입니다.

최소 준수(프롬프트/규칙 문서)
- 필수 섹션: Problem / Scope / Invariants / DoD / Failure / Reason Codes / Rollback / References
- References: 빈 칸 금지(논문/표준/공식문서/수식 등 근거 최소 1개)
- 스탬프: Owner / Last-Reviewed 등 포함

리뷰 포인트(사람 검토)
- prompt-lint는 구조/형식 하한선을 검사합니다.
- References의 진위/정합성은 Code Owner 리뷰에서 확인합니다.

## 6-4) PR Conversation 코멘트용(복붙)

[SEALED] Prompt QA 강제 체계(Q1~Q3) 종결
- prompt-lint: PR #102 + #105 (merged)
- CODEOWNERS: PR #104 (merged)
- 품질 계약(PROMPT_QUALITY_BAR_V1): PR #106 (merged)
- SSOT 단일 진실원: PR #109 (merged)
- SSOT 경로 변경은 prompt-lint PASS + Code Owner 승인 없으면 main 머지 불가
