# Prompt QA(Q1~Q3) 운영 종결(SEALED) — SSOT (Single Source of Truth)

Prompt-Version: 1.0
Owner: Platform Team (Platform Owner + Integration Owner)
Last-Reviewed: 2026-01-16

## Problem
Prompt QA(Q1~Q3)는 “정책/권고”가 아니라 GitHub의 브랜치 보호(Required status checks) + CODEOWNERS(코드오너 리뷰 강제) + 계약 문서 봉인으로 인해
“조건 미충족 = 물리적으로 머지 불가”인 상태로 운영 종결(SEALED)되었습니다.

또한 정본은 PR #109로 봉인된 SSOT 파일 1개이며, 앞으로는 이 파일만을 단일 진실원으로 참조합니다.
(명칭/이름/코드명 논의는 본 문서 범위 밖)

## Scope
### MUST include
- Prompt QA(Q1~Q3) 운영 종결(SEALED)
  - prompt-lint 게이트
  - 브랜치 보호(required checks)
  - CODEOWNERS(리뷰 강제)
  - 품질 계약(PROMPT_QUALITY_BAR_V1) 봉인
- 운영 함정 2개를 분리 고정
  - 함정 A: 상태 미보고(Waiting/Expected)
  - 함정 B: skipped 우회(조건식으로 실행 회피)
- “정본은 SSOT 파일 1개만 참조” 운영 고정

### MUST NOT include
- 명칭/이름/코드명 논의(본 문서 범위 밖)
- 원문/라인 덤프/로그 전문(본 SSOT는 meta-only)

## Invariants
- Output-based only: 말로 PASS 금지, 출력/체크/기록으로 판정
- meta-only: 원문/라인/로그 전문 출력 금지
- Fail-Closed: 애매하면 막고 reason_code를 남김
- 1 PR = 1 Purpose

## DoD
- Required status check(prompt-lint)가 PASS가 아니면 main 머지 불가
- SSOT 경로 변경 시 Code Owner 승인 없으면 main 머지 불가
- 품질 계약(PROMPT_QUALITY_BAR_V1)이 main에 봉인되어 기준이 흔들리지 않음
- 정본은 본 SSOT 파일 1개로 참조 고정(복사본 확산 방지)

## Failure Modes (FMEA) & Threat Model
- FM-A: required check가 아예 보고되지 않음 → Waiting/Expected(“status to be reported”)로 머지 멈춤
  - Control: 모든 PR에서 required check 상태가 항상 보고되도록 유지 (PR #105 정렬)
  - reason_code=PQA_EXPECTED_WAITING

- FM-B: 워크플로는 떴지만 required job/step이 조건식으로 skipped → skipped가 통과로 취급되어 차단 약화 가능
  - Control: required check job/step은 조건식으로 쉽게 skipped 되지 않도록 유지
  - reason_code=PQA_SKIPPED_BYPASS

- FM-C: required check “이름” 혼선(체크 런/잡) → 잘못된 항목을 required로 걸어 무력화/오판 위험
  - Control: Required status check는 GitHub UI에 표시되는 체크 런/잡 이름 기준으로 고정하고, job 이름은 유니크하게 유지
  - reason_code=PQA_CHECKNAME_MISMATCH

- FM-D: CODEOWNERS 미적용(위치/우선순위/베이스 브랜치 조건 불충족) → 리뷰 강제 누락
  - Control: CODEOWNERS는 base 브랜치(main)에 존재해야 하며, .github/ → repo root → docs/ 우선순위를 준수
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
- PR #105 merged: 모든 PR에서 prompt-lint 상태 보고(Waiting/Expected 함정 정리)
- PR #104 merged: CODEOWNERS 실제 계정 연결(SSOT 경로 code owner 지정)
- PR #106 merged: PROMPT_QUALITY_BAR_V1 봉인(“박사급 정의 + Gate PASS 전제”)
- PR #107 merged: 후속(범위/DoD 키는 PR Files changed + checks 출력로 meta-only 확정 후 편입)
- PR #108 merged: 후속(범위/DoD 키는 PR Files changed + checks 출력로 meta-only 확정 후 편입)
- PR #109 merged: SSOT 단일 진실원 봉인(본 파일을 정본으로 사용)

### GitHub Docs (external behavior)
- Required status checks: https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-protected-branches/about-required-status-checks
- Protected branches: https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-protected-branches/about-protected-branches
- Code owners: https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/customizing-your-repository/about-code-owners

---

# 복붙 블록 4종 (SSOT에서만 복사하여 사용)

## 6-1) 팀 내부 공지용(복붙)

제목
[SEALED] Prompt QA(Q1~Q3) 운영 종결 — SSOT 단일 진실원 기준

본문
최종 결론: Prompt QA는 개인 역량이 아니라 시스템 하한선(머지 차단)으로 강제되는 체계로 운영 종결(SEALED)되었습니다.

정본(단일 진실원)
- docs/ops/contracts/PROMPT_QA_Q1_Q3_SEALED_SSOT.md (PR #109 merged)

근거(SSOT 입력 기준, merged)
- PR #102 / #105 / #104 / #106 merged
- 후속: PR #107 merged, PR #108 merged (범위/DoD 키는 Files changed + checks로 meta-only 확정 후 편입)

운영 표준(고정)
- SSOT 경로 변경은 prompt-lint(PASS) + Code Owner 승인(완료) 동시 충족 없으면 main 머지 불가
- required check job/step은 조건식으로 쉽게 skipped 되지 않도록 유지(우회 차단)

실무 규칙
- SSOT 경로 변경 PR은 prompt-lint PASS + Code Owner 승인 전까지 main 머지 불가
- 테스트/검증용 PR은 머지 금지(확인 후 Close + 브랜치 삭제)

## 6-2) 타팀 공유용(복붙)

제목
[공지] Prompt QA Standard v1.0 운영 강제 — SSOT 단일 진실원 기준

본문
Prompt Registry(SSOT) 관련 변경은 이제 CI와 리뷰 규칙이 자동 강제되며,
prompt-lint PASS + Code Owner 승인 없이는 main에 머지되지 않습니다.

정본(단일 진실원)
- docs/ops/contracts/PROMPT_QA_Q1_Q3_SEALED_SSOT.md (PR #109 merged)

자동 차단 예시
- 필수 섹션 누락 / References 비어 있음 / 스탬프 누락 → CI FAIL → 머지 차단

## 6-3) 알고리즘팀 안내용(R2 준수, 복붙)

제목
[R2 준수] 알고리즘 프롬프트는 References 근거 포함 필수 (prompt-lint 자동 검증)

본문
알고리즘 관련 프롬프트/규칙 문서도 SSOT 경로 변경으로 분류되며,
prompt-lint PASS가 아니면 main 머지 불가입니다.

최소 준수
- 필수 섹션: Problem / Scope / Invariants / DoD / Failure / Reason Codes / Rollback / References
- References: 빈 칸 금지(근거 1개 이상)
- 스탬프: Owner / Last-Reviewed 포함

리뷰 포인트
- 형식은 CI가 검사하고, References 정합성은 Code Owner 리뷰에서 확인합니다.

## 6-4) PR Conversation 코멘트용(초단문 5줄, 복붙)

[SEALED] Prompt QA(Q1~Q3) 운영 종결 — SSOT 단일 진실원(PR #109)
- Required check: prompt-lint (PASS 아니면 머지 불가)
- SSOT 경로 변경은 prompt-lint PASS + Code Owner 승인 없으면 main 머지 불가
- required check 함정(Waiting/Expected vs skipped) 재발 방지: 상태 항상 보고 + skipped 우회 차단 유지
- 정본: docs/ops/contracts/PROMPT_QA_Q1_Q3_SEALED_SSOT.md
