# ALGORITHM_EXECUTION_DIRECTIVE_V1_1

## 0. 한 줄 정의
우리 제품의 본체는 직원 및 회사 내 허가된 모든 사람과 부서가 실제 업무 중 질문·분석·초안·검토·파일 수정·프로젝트 관리를 요청했을 때 컴퓨터 내부에서 AI가 작동하는 버틀러이며, 알고리즘팀의 역할은 이 버틀러의 실제 두뇌를 만드는 것이다.

## 1. 현재 판정
- 운영판(SSOT/verify/fail-closed/meta-only/공급망)은 강해졌다.
- 하지만 AI 본체의 실체(기기별 실행/모델 사다리/예산 기반 라우팅)는 아직 부족하다.

## 2. 즉시 채택 사항
1. 기계 SSOT(.txt/.json)와 설명 문서(.md) 분리
2. workflow YAML parse guard를 독립 required workflow로 분리
3. stdout은 DoD 키만, 진단은 JSON 리포트로 분리
4. latency 단위는 현재 SSOT/게이트와 정합되게 유지하고, 고해상도 내부 측정(us/ns) 승격은 관련 계약과 함께 별도 PR로 정렬
5. 모델팩을 SBOM / provenance / TUF 체인에 포함
- 현재 외부 계약(리포트/게이트/예산 지표)은 ms 기준을 유지한다.
- 내부 고해상도 측정값은 us 또는 ns를 사용할 수 있으나, 이를 SSOT/게이트로 승격할 때는 지표명, 예산, workflow, verify를 같은 변경에서 함께 정렬한다.

## 3. 필수 추가 과제
1. DEVICE_PROFILE_METRICS_SSOT_V1
2. MODEL_PACK_CATALOG_V1
3. ROUTING_BY_BUDGET_WITH_HYSTERESIS_V1
4. EXEC_MODE_AI_QUALITY_GATES_V1
5. MODEL_PACK_SBOM_AND_TUF_WIRING_V1

## 4. 우선순위
1. device profiling
2. model pack catalog
3. routing by budget + hysteresis
4. exec-mode AI quality gates
5. model pack supplychain wiring

## 5. 완료 기준
- 기기 프로파일링이 meta-only 출력으로 표준화되어야 한다.
- 모델팩 카탈로그가 기계 SSOT로 고정되어야 한다.
- pack 선택은 예산 기반 + fail-closed + hysteresis를 가져야 한다.
- exec-mode 결과에 pack_id / device_class_id / reason_code가 포함되어야 한다.
- 모델팩이 SBOM / provenance / TUF 체인 안에 들어가야 한다.

## 6. 금지
- 원문/원문조각 외부 전송
- 원문/장문 로그/리포트/예외 출력
- 기계 SSOT를 md 설명 문서에 직접 파싱하는 구조
- 숫자 증빙 없이 "개선됨" 주장
