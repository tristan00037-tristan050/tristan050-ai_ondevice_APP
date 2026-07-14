# v2.8 명세 교정 기록

## IC-01 — 공격시험 58/60 불일치

본문 §15.2와 §20.1은 58건이라고 쓰지만 정본 `attack_matrix_v2.8.csv`에는 `ATK-001`부터 `ATK-060`까지 60행이 있고 검증보고서도 60행이라고 확인합니다. 더 강한 기계판독 정본을 채택해 60건 전부 자동화했습니다.

## IC-02 — 46개 결함 추적표 오매핑

원본 `defect_traceability_46_v2.8.csv`에는 독립 verifier 결함이 OS egress 승인 ID에, dual resident 결함이 worker ID에, 에너지 결함이 evidence DAG ID에 연결되는 등 영역 오매핑이 다수 있습니다. 원본은 감사 추적을 위해 보존하고 `defect_traceability_46_v2.8.corrected.csv`에서 결함 제목 기준으로 acceptance·attack ID를 다시 연결합니다.

## IC-03 — Metal 초기 할당량 0

지시서 §8.1은 모든 byte 값이 0보다 커야 한다고 쓰지만 `MTLDevice.currentAllocatedSize`는 preload 전 정상적으로 0일 수 있습니다. RSS·available memory·recommended working set은 양수, 현재 Metal 할당량은 0 이상으로 검증합니다.

## IC-04 — G1 상태 schema

원본 `final_status.schema.json`은 `G1_READY`를 허용하지만 본문은 M4 없이는 선언할 수 없다고 명시합니다. 이 구현의 schema에서는 `G1_READY` enum을 제거했고 runtime activation은 항상 0으로 유지합니다.

## IC-05 — 코드 전달 검증과 M3 증거 검증

receipt가 없는 코드 패키지를 M3 artifact PASS로 처리하면 `ATK-001`이 재발합니다. 독립 검증기는 `code-delivery`와 `m3-evidence`를 분리합니다. 전자는 패키지 무결성만 PASS하고 M3 주장을 명시적으로 false로 유지하며, 후자는 필수 receipt 16종 이상과 final DAG가 없으면 차단합니다.

## IC-06 — RFC 8785 숫자 프로필

Python과 JavaScript의 부동소수점 문자열 차이를 제거하기 위해 receipt는 safe integer 기본단위를 사용합니다. 정책 소수는 최대 6자리 decimal string 또는 ppm 정수로 승인하고 내부 연산은 ppm으로 변환합니다. NaN·Infinity·JSON float는 차단합니다.

## IC-07 — 대표 warmup 범위

본문은 epoch마다 candidate별 대표 warmup 2회, 총 4회를 요구합니다. 이전 구현처럼 fixture마다 warmup을 반복하지 않고, 각 epoch의 정렬된 대표 fixture 1개에서 A·B 각각 2회만 수행합니다. measured run은 모든 fixture에서 AB/BA로 유지합니다.

## IC-08 — verify 단계의 네트워크 순수성

소스 동기화의 `git fetch`는 실행 준비 단계이며 verifier 내부 동작이 아닙니다. provenance verifier는 이미 존재하는 로컬 전체 OID와 ancestry만 판정하고 다운로드나 fetch를 수행하지 않습니다.
