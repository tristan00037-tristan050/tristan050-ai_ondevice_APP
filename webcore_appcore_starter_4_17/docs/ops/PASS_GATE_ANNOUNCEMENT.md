# PASS 선언 기준(신규 지침) — 테스트/보완 완료 전 PASS 금지

## 규칙

테스트/보완팀은 앞으로 테스트/보완 작업이 완료되기 전에는 PASS를 선언하지 않는다.
PASS(CLOSED & SEALED)는 아래 조건을 모두 만족할 때만 선언한다.

## PASS 조건 (10개 모두 충족)

1. 원샷 검증 스크립트(VERIFY_*.sh) 1줄 실행으로 PASS가 재현됨
2. SSOT 증거 파일이 고정 경로로 항상 생성되며(meta-only 자동 점검 PASS), 리뷰어가 즉시 확인 가능
3. 품질/회귀 게이트 PASS(또는 의도된 FAIL 조건이 명시적으로 충족)
4. git status --porcelain 빈 출력(working tree clean) + 런타임 산출물 추적 0(.gitignore 봉인)
5. 커밋/푸시 완료 및 커밋 해시로 증빙 가능
6. 범위(Scope)와 목표(Goal)가 SSOT 문서/공지에 1줄로 고정되어 있음
7. 원샷 실행 결과가 저장되고(로그 경로 출력), tail로 재현 가능한 증빙이 있음
8. SSOT 증거 파일은 meta-only 준수(자유 텍스트 금지, PII/시크릿/URL/IP/이메일/토큰/키 금지, 값은 숫자/불리언/짧은 열거형만 허용) 자동 점검 PASS
9. .gitignore가 런타임 산출물을 추적하지 않도록 봉인되어 있음
10. 위 1~9 증빙이 검토팀/개발팀 공지(복붙 정본)에 포함됨

## PASS 선언 전 필수

```bash
bash scripts/ops/verify_pass_gate.sh --verify <VERIFY_*.sh> --ssot <SSOT_FILE>
```

**Exit 0 + "PASS: CLOSED & SEALED eligible" 출력 시에만 PASS 선언 가능.**

하나라도 실패하면 exit 1 + 실패 원인 + 로그 tail이 자동 출력 → "PASS 선승인" 구조적으로 불가

## 판정 기준

위 조건 중 하나라도 미충족이면 판정은 **Block/Proceed(조건부)**로 유지하며, 보완 후 재검증한다.

## 참고 문서

- PASS Gate Checklist: `docs/ops/PASS_GATE_CHECKLIST.md`
- 자동 검증 스크립트: `scripts/ops/verify_pass_gate.sh`

