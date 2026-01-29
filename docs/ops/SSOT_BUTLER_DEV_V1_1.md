# Butler 개발 지침(SSOT) v1.1 — 단일 정본

목적
- main에서 봉인된 Butler Gateway(ALGO-CORE/Gateway) 기준선을 절대 깨지 않으면서,
  Butler Runtime / Model Pack / 운영 허브 / Tiers를 병렬 개발하고 단계적으로 통합한다.

## 최상위 불변 계약(불가침)
1) 기준선 불가침: main에서 scripts/verify/verify_repo_contracts.sh 결과 EXIT=0이 아니면 신규 트랙 통합/확대 금지
2) prod fail-closed 불가침: 키 누락/불일치인데 서비스 기동하면 즉시 BLOCK(완화 금지)
3) 키/증빙 불가침: 기존 repo-guards 키 삭제/이름 변경 금지(확장은 "추가 키"만)
4) /v1/os/algo/three-blocks 불가침: 3블록 + manifest + signature + 증빙 헤더 유지
5) 외부 AI 호출 0 불가침: 추론 경로에서 외부 AI API 호출 0
   - 이중화: 코드 레벨(host allowlist) + 배포 레벨(egress deny)

## 용어(SSOT)
- Butler: 제품군 통합 명칭
- Butler Gateway: 정책/증빙/서명/차단 레이어(현재 main 기준선)
- Butler Runtime(실행 추론기): 모델(가중치)을 실행하는 엔진 프로그램(모델 자체가 아님)
- Butler Model Pack: 부서/업무 특화 모델/리소스 패키지(서명된 배포 단위)
- Butler 운영 허브: 원문 수집 없이 메타 기반 운영/지원/개선 레이어
- Butler Tiers: 지표 기반(S/M/L 등) 성능/과금 레벨

외부 AI 호출 0 정의
- 추론(질문→답) 수행 중 인터넷/클라우드 외부 AI API 호출 경로 0
- 오픈 모델 사용은 가능(모델 파일을 고객 내부로 반입해 내부 실행)

## 현재 기준선(이미 main에서 봉인)
- ALGO-CORE-01~03: meta-only fail-closed, 3블록 고정, signed manifest+verify, P95 gate, delivered keyset
- ALGO-CORE-04: /v1/os/algo/three-blocks 런타임 배선 + prod 키 없으면 부트 fail-closed
- ALGO-CORE-05: 런타임 호출 증빙(Smoke Proof) 문서 봉인
- ALGO-CORE-06: prod 키 관리 SSOT/템플릿/keygen + keygen CommonJS 안전성 + repo-guards 강제
- 게이트웨이 배포 가이드: docs/ops/ALGO_CORE_GATEWAY_DEPLOYMENT.md + 문서 게이트(repo-guards)

## 구조(혼선 0)
Layer A: 계약(Contract)
- Request: meta-only + request_id + dept + tier + 정책/버전
- Response: 3블록 + manifest.sha256 + signature + 증빙 헤더
- Measure: P95 훅(입력 완료→3블록 렌더 완료)

Layer B: 실행(Execution)
- Gateway / Runtime / Model Pack / 운영 허브 / Tiers

Layer C: 게이트(Gate)
- DoD 키 출력 + fail-closed 재현 + EXIT=0로만 전진

## 통합 순서(고정)
- Runtime v0 → Model Pack v0 → 운영 허브 v0 → Tiers v0
- 통합 단계: OFF → Shadow(관측) → 제한적 ON(고객 1곳) → 확대
- 모든 신규 기능: Feature Flag 기본 OFF

## 실행 큐(P0)
- Track 1(Gateway): 상시 실행/내부망 제한/헬스/로그/재시작 표준화
- Track 2(Runtime v0): 내부망 only 스켈레톤 + egress deny/allowlist + Shadow 연결(meta-only)
- Track 3(Model Pack v0): 부서 1개 팩 + signed manifest + install→load→gateway 재현(fail-closed)
- Track 4(운영 허브 v0): 메타 스키마 SSOT + 원문 금지 가드 + 리포트 v0
- Track 5(Tiers v0): S/M/L 지표 정의 SSOT + 제한 정책 + 강제(fail-closed)

판정(고정)
- 모든 PR은 verify_repo_contracts.sh EXIT=0 + DoD 키=1 출력으로만 완료 처리
