# PASS Gate Checklist (SSOT)

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
