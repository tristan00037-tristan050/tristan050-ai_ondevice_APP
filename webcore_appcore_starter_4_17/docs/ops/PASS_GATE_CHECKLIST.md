# PASS Gate Checklist (SSOT)

## SSOT v3.4 팀 규칙

본 문서는 AI 온디바이스 플랫폼의 단일 기준(SSOT)이며, 모든 팀은 본 문서와 정본 게이트 출력 외 기준으로 개발/승인/반려를 하지 않는다.

각 팀의 책임은 '정본 산출물'로 종료되며, 산출물 없이 말로 완료를 주장할 수 없다.

## Step4-B SSOT v1.1 (Remote-First Truth)

### Remote-First Truth
"파일 존재/반영 여부의 단일 진실원은 git fetch 이후의 origin/main이다. main(로컬) 기준 판정은 금지한다."

### Fail-Closed 확인 순서
"모든 PR 준비/검토는 fetch → origin/main 확인 → 필요 시 pull 순서를 강제한다. 이 순서를 생략한 '없다/있다' 보고는 반려한다."

### Identical PR 금지
"git rev-list --left-right --count origin/main...HEAD가 0 0이면 PR 생성 금지(비교 불가/중복 작업 차단)."

### Reviewer Hard Gate
"PR 생성/검토 전 git fetch 이후 origin/main 기준 존재 확인을 수행하지 않았으면 Block(오판 기반 중복 PR은 가장 큰 비용)."

규칙: 아래 10개 중 1개라도 미충족이면 판정은 Block/Proceed(조건부)이며 PASS 선언 금지.

1) 범위(Scope)와 목표(Goal)가 SSOT 문서/공지에 1줄로 고정되어 있다.  
2) 원샷 검증 스크립트(VERIFY_*.sh)가 존재하고, 실행 커맨드가 1줄로 고정되어 있다.  
3) 원샷 실행 결과가 저장되고(로그 경로 출력), tail로 재현 가능한 증빙이 있다.  
4) SSOT 증거 파일(고정 경로)이 성공/실패와 무관하게 항상 생성된다.  
5) SSOT 증거 파일은 meta-only 준수(자유 텍스트 금지, PII/시크릿/URL/IP/이메일/토큰/키 금지, 값은 숫자/불리언/짧은 열거형만 허용) 자동 점검 PASS.  
6) 품질 게이트(Regression Gate 등) PASS 또는 의도된 FAIL 조건(strict=0→exit1)이 명확히 충족된다.  
7) git status --porcelain 이 빈 출력(working tree clean)이다.  
8) .gitignore 가 런타임 산출물을 추적하지 않도록 봉인되어 있다.  
9) 변경사항은 커밋/푸시되어 있고(커밋 해시 제시), 재실행해도 동일 판정이 나온다.  
10) 위 1~9 증빙이 검토팀/개발팀 공지(복붙 정본)에 포함되었다.

## PASS 선언문 템플릿(복붙 정본)
- 실행(원샷): <command 1줄>
- SSOT 증거 파일: <path>
- meta-only: PASS
- 위생: git status --porcelain 빈 출력
- 커밋: <sha>
- 판정: PASS (CLOSED & SEALED)
