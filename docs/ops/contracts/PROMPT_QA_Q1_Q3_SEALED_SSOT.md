# Prompt QA 강제 체계(Q1~Q3) 운영 종결(SEALED) — SSOT

## 0) 라벨 정정(고정)
- “개발팀 전달용”은 부적절. 우리는 개발팀이므로: 팀 내부 공지용(복붙)
- 외부 공유: 타팀 공유용(복붙)

## 1) 문서 범위(고정)
포함
- Prompt QA 강제 체계(Q1~Q3) 운영 종결(SEALED): 게이트/리뷰/계약 봉인 + 머지 차단(merge-blocking)
- SSOT 경로 변경이 CI(prompt-lint) + Branch protection(Required checks) + CODEOWNERS로 강제되는 구조
- 팀 내부/타팀/알고리즘팀/PR 코멘트용 복붙 블록(6-1~6-4)

제외
- 명칭/코드명/이름 논의(범위 밖)

## 2) 실행 결과 SSOT 요약(merged=true 기준)
- Q1(Gate): prompt-lint 게이트 구축 → PR #102 merged
- Q1 보완(상태 보고): 모든 PR에서 prompt-lint 상태 보고 → PR #105 merged
  - 효과: required check가 Waiting/Expected로 대기하며 머지가 막히는 함정 제거(항상 상태 보고 정렬)
- Q2(Review 강제): CODEOWNERS 실제 계정 연결 → PR #104 merged
- Q3(품질 계약 봉인): “박사급 정의 + Gate PASS 전제” 문구 봉인 → PR #106 merged
  - 계약 키: PROMPT_QUALITY_BAR_V1

## 3) 운영 근거(요지)
- Required status checks: required check가 PASS 전에는 보호 브랜치(main)에 머지 불가
- Code Owners 강제: “Require review from Code Owners” 활성 시 지정 경로 변경은 Code Owner 승인 없이는 머지 불가
- CODEOWNERS 조건: .github/ → root → docs/ 우선순위, PR base 브랜치(main)에 존재해야 적용

## 4) 운영 표준(고정)
시스템 강제 정의(한 문장)
- “SSOT 경로 변경은 prompt-lint(PASS)와 Code Owner 승인(완료)이 동시에 만족되지 않으면 main 머지가 불가능하다.”

Required check
- prompt-lint (PASS 아니면 머지 불가)

SSOT 대상 경로(고정)
- .cursor/rules/**
- docs/ops/cursor_prompts/**
- docs/ops/contracts/**

운영 안전 문장(고정)
- required check에 해당하는 job/step은 조건식으로 skipped 되지 않도록 유지한다.

## 5) 실무 규칙(팀 공통, 단문 고정)
- SSOT 경로 변경 PR은 prompt-lint PASS + Code Owner 승인 전까지 main 머지 불가
- 테스트/검증 목적 PR은 머지 금지(확인 후 Close + 브랜치 삭제로 종료)

## 6) 복붙 블록 4종 정본

6-1) 팀 내부 공지용(복붙)
제목
[SEALED] Prompt QA 강제 체계(Q1~Q3) 운영 종결 (prompt-lint + CODEOWNERS + 품질 계약 봉인)

본문
- 근거: PR #102, #105, #104, #106 merged
- 운영 표준: Required status check=prompt-lint, SSOT 경로 변경은 prompt-lint PASS + Code Owner 승인 없으면 main 머지 불가
- 실무 규칙: 테스트/검증 PR은 머지 금지(확인 후 Close + 브랜치 삭제)

6-2) 타팀 공유용(복붙)
제목
[공지] Prompt QA Standard v1.0 운영 강제 시작 (SSOT 경로: prompt-lint 필수 통과 + Code Owner 승인)

본문
- SSOT 경로 변경은 prompt-lint PASS + Code Owner 승인 없이는 main 머지 불가
- 위반 예: 필수 섹션/References/스탬프 누락 → CI FAIL → 머지 차단
- 기준 문서: PROMPT_QUALITY_BAR_V1(main 봉인, PR #106 merged)

6-3) 알고리즘팀 안내용(R2 준수, 복붙)
제목
[R2 준수] 알고리즘 프롬프트는 References 근거 포함 필수 (prompt-lint 자동 검증)

본문
- SSOT 경로 변경으로 분류되며 prompt-lint PASS 아니면 main 머지 불가
- 최소 준수: Problem/Scope/Invariants/DoD/Failure/Reason Codes/Rollback/References + Owner/Last-Reviewed
- 리뷰 포인트: prompt-lint PASS 이후에도 References 진위/정합성은 리뷰에서 확인

6-4) PR Conversation 코멘트용 초단문 5줄(복붙)
[SEALED] Prompt QA 강제 체계(Q1~Q3) 종결
- prompt-lint: PR #102 + 상태 보고 보완 PR #105 (merged)
- CODEOWNERS 실계정 연결: PR #104 (merged)
- 품질 계약(PROMPT_QUALITY_BAR_V1) 봉인: PR #106 (merged)
- SSOT 경로 변경은 prompt-lint PASS + Code Owner 승인 없으면 main 머지 불가
