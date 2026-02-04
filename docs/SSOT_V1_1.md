
# AI 온디바이스 전사 플랫폼 SSOT v1.1
기준 시점: 2026-02-04 (KST)

이 문서는 지금까지의 합의(개발/검토/테스트/기획/알고리즘/재검토/실행팀 의견)를 단일 진실원(SSOT)으로 고정합니다.  
모든 개발/리뷰/테스트/배포 판정은 이 문서와 기준선 출력으로만 인정합니다.

---

## 1) 제품 정의

### 1.1 한 문장 정의
회사 PC/태블릿/허가된 스마트폰에서 AI가 먼저 실행되어 업무를 돕고, 회사 내부 서버는 팀/권한/정책/승인/기록/업데이트를 통제하며, 기기 성능이 부족할 때만 회사 내부 보조 컴퓨트가 최소 정보로 계산을 돕는 전사 AI 플랫폼을 만듭니다.

### 1.2 우리가 파는 것(상품)
- “더 똑똑한 AI”가 아니라, 기업이 돈을 내는 운영 조건(통제/감사/배포 안전/유출 방지)을 **기술로 강제**하는 제품
- 외부 AI로 나가는 길을 끊고(기본 차단), 내부 대체 경로와 승인 흐름으로 섀도우 AI를 흡수

---

## 2) 확실한 차별성(경쟁 포지셔닝)

경쟁사(OS/디바이스 기본 기능)는 “개인 경험”에 강하고, 우리는 “기업 전사 운영”에 강합니다.  
차별성은 아래 4축을 **기본값으로 강제**하는 데 있습니다.

1) 외부 전송 기본 0(기본 차단) + 내부 대체 경로 제공  
2) 전사 정책/권한/승인/감사가 자동으로 붙음(사람 운영 금지)  
3) 업데이트는 검증 통과 출력이 있어야만 적용(적용 실패=적용 0 + 상태 불변)  
4) 원문 저장 0(meta-only 기록) + request_id로 전 구간 조인

---

## 3) 목표 타겟 시장(명확히 고정)

### 3.1 1차 타겟(우선순위)
- 외부 AI 사용이 곤란하거나(망분리/내부망 중심), 감사/규정이 강한 조직
- 개발 조직을 보유하고 코드/로그/문서 유출 리스크가 큰 기업

### 3.2 2차 타겟(확장)
- 전사 문서/업무 자동화 니즈가 큰 중견~대기업(혼합 OS 환경 포함)

금지: 소비자형 범용 비서 시장으로 포지셔닝하지 않습니다.

---

## 4) 매출 모델(개발 지시서에 포함, 고정)

과금 축 3개로 고정합니다.
1) 서버(문지기/정책/운영) 조직 단위 연간 요금  
2) 좌석(기기) 수 기반 요금(또는 번들)  
3) 내부 보조 컴퓨트(선택 옵션) 등급 요금 또는 사용량 요금  

초기 판매 패키지(MVP):
- 전사 공통 3 시나리오 E2E + 승인 없이 반출 0 + 외부 전송 0 + 운영 콘솔 v0

---

## 5) 제품 구조(4 레이어, 고정)

1) 기기 레이어(기본)
- 온디바이스 우선 실행
- 외부 전송 기본 차단
- 팀/개인 스위치(업무팩) 적용

2) 문지기 서버(사내 통제)
- 최소 RBAC(Phase 1) / SSO(Phase 2)
- 정책 검사/차단, 승인 흐름
- 사내 시스템 커넥터(문서/티켓) 권한 포함

3) 사내 보조 컴퓨트(선택)
- 기본 OFF
- SSOT 허용 조건 충족 시에만 ON
- 최소 정보만 처리, 원문 저장 0

4) Ops Hub(운영/감사)
- meta-only 이벤트 저장
- request_id 조인
- 운영 콘솔(사용량/차단 사유/승인 이력/업데이트 이력)

---

## 6) PASS 단일 앵커(불가침)

PASS는 오직 아래 출력으로만 인정합니다.
```bash
bash scripts/verify/verify_repo_contracts.sh ; echo "EXIT=$?"
```
Expect: EXIT=0

규칙:
- 기존 DoD 키 삭제/의미 변경 금지(추가만 허용)
- 근거는 출력/키/재현 커맨드/SEALED 문서로만 제출

---

## 7) SSOT v1.1 고정 규칙(문장 그대로)

### 7.1 M9 선행 봉인 5개(Phase 1보다 반드시 먼저 PASS)
1) verify 순수성 전수화: verify는 판정만 수행한다. 설치/다운로드/네트워크는 workflow preflight에서만 수행한다.  
2) meta-only validator 단일 소스: 저장 전 차단, 중복 구현 0, 우회 경로 0.  
3) trace 저장 봉인: DB 스키마/멱등/동시성(동시 ingest에서도 부분 쓰기 0) 봉인.  
4) trace 보안 잠금: 기본 로컬-only(또는 인증 필수 중 1개를 SSOT로 고정). 0.0.0.0 노출 경로 0.  
5) 출력 일관성(D0 동급): 동일 입력 2회 실행 시 핵심 결과 해시 동일을 게이트로 봉인.  

### 7.2 Phase 1 병렬 착수(반드시 동시에 진행)
M9 전체 완료를 기다리지 않는다. 단, Phase 1 병렬 범위는 다음 3개로 제한한다.
1) 온디바이스 실제 모델 실행 최소 1개 경로  
2) 전사 공통 3 시나리오 E2E(커넥터는 meta-only 최소로 시작)  
3) 반출 승인 흐름(승인 없이 반출 0)  

### 7.3 Phase 1 금지/허용
- SSO는 Phase 2 고정. Phase 1은 테스트 가능한 최소 RBAC만 허용한다.  
- 보조 컴퓨트는 기본 OFF이며 SSOT 숫자/조건을 만족할 때만 ON 한다. 조건 외 라우팅은 BLOCK 또는 온디바이스 강제다.  

### 7.4 원문 저장 0 정의(범위 확장 포함)
- “원문 저장 0”은 디스크/DB/이벤트뿐 아니라 로그/예외/오류리포트/분석 이벤트에도 원문(또는 원문 조각)이 포함되면 즉시 BLOCK이다.  
- 메모리에서의 일시 처리는 허용하되, 기록은 meta-only만 남긴다.  

### 7.5 업무팩 우회 금지(추가 고정)
업무팩(팀/개인 스위치)은 템플릿/룰/용어 확장만 가능하며, 데이터 이동/반출/정책판단/기록/검증/라우팅은 반드시 공통 코어를 통한다. 우회 경로는 즉시 BLOCK.

---

## 8) 최종 실행 계획(트랙 A/B)

### 8.1 트랙 A: M9 선행 봉인 5개(PR 순서 고정)
A1) VERIFY_PURITY_FULL_SCOPE
- DoD: VERIFY_PURITY_FULL_SCOPE_OK=1, VERIFY_PURITY_ALLOWLIST_SSOT_OK=1
- BLOCK: scripts/verify/** 내 설치/다운로드/네트워크 명령 재유입

A2) META_VALIDATOR_SINGLE_SOURCE
- DoD: META_ONLY_VALIDATOR_SINGLE_SOURCE_OK=1, META_ONLY_VALIDATOR_NO_DUPLICATION_OK=1
- BLOCK: 중복 validator, 저장 후 필터 경로, 우회 경로

A3) TRACE_DB_PROMOTION
- DoD: OPS_HUB_TRACE_SERVICE_DB_SCHEMA_OK=1, OPS_HUB_TRACE_DB_UPSERT_OK=1, OPS_HUB_TRACE_SERVICE_CONCURRENCY_OK=1
- BLOCK: 중복 저장, 부분 쓰기, 저장 전 validator 미적용

A4) TRACE_SECURITY_LOCKDOWN
- DoD: OPS_HUB_TRACE_LOCAL_ONLY_OR_AUTH_OK=1
- BLOCK: 0.0.0.0 바인딩, 무권한 ingest/report

A5) OUTPUT_CONSISTENCY_D0_MIN
- DoD: ALGO_D0_MIN_OK=1 (Phase 1 최소 D0)

### 8.2 트랙 B: Phase 1 상품 체감(병렬, 범위 제한)
B1) ONDEVICE_MODEL_EXEC_V0
- DoD: ONDEVICE_MODEL_EXEC_V0_OK=1, MODEL_PACK_VERIFY_REQUIRED_OK=1

B2) SCENARIO_DOC_SEARCH_E2E_V0
- 최소 DoD 4키: *_ALLOW_OK, *_BLOCK_OK, *_META_ONLY_OK, *_REQUEST_ID_JOIN_OK

B3) SCENARIO_WRITE_APPROVE_E2E_V0
- 최소 DoD 4키 + 승인 없이 반출 0(Preview→Approve, audit_event 필수)

B4) SCENARIO_HELPDESK_TICKET_E2E_V0
- 최소 DoD 4키(티켓 연동은 서버 대행)

B5) EXPORT/DLP UX v0
- “차단만” 금지: 내부 대체 경로 + 승인 요청 UX 필수

---

## 9) 운영/검증 최소 정책(Phase 1)

### 9.1 시나리오별 DoD 키 폭증 방지
Phase 1에서는 시나리오당 필수 4키만 강제한다.
- *_ALLOW_OK=1
- *_BLOCK_OK=1
- *_META_ONLY_OK=1
- *_REQUEST_ID_JOIN_OK=1

### 9.2 증빙 규칙
- “동작했다”가 아니라 “실패해야 할 때 실패하고, 성공해야 할 때만 성공”이 출력으로 증빙되어야 한다.

---

## 10) 템플릿/운영 문서 위치
- PR 템플릿: docs/PR_TEMPLATES/
- 실행팀 리포트 템플릿: docs/EXECUTION_TEAM/ISSUES/_TEMPLATE.md
