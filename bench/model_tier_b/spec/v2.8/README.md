# Butler 모델티어 B단계 수정개발지시서 v2.8

이 패키지는 v2.7의 46개 결함과 문서 간 충돌을 교정한 개발 정본이다.

## 읽는 순서

1. `Butler_모델티어_B단계_수정개발지시서_v2.8.pdf`
2. `defect_traceability_46_v2.8.csv`
3. `acceptance_matrix_v2.8.csv`
4. `attack_matrix_v2.8.csv`
5. JSON schema/template 5종
6. `보완팀5_감사보고서_v2.8.md`와 `검증결과_v2.8.md`

## 현재 상태

```text
SPEC_REVIEW_PASS=YES
CODE_IMPLEMENTATION_PASS=NO
ALL_46_DEFECTS_CLOSED=NO
M3_START_ALLOWED=NO
M3_EVIDENCE_PASS=NO
G1_READY=NO
RUNTIME_ACTIVATION_ALLOWED=0
```

`UNSET` 값은 구현팀이 추정해 채우는 기본값이 아니다. 승인자·정본 저장소·대상 M3에서 실제 증거로 해소하지 못하면 BLOCK한다.

## 무결성

`SHA256SUMS`는 패키지 내부 파일을 검증한다. 실제 제품 release는 inner immutable payload를 별도 서명하고 trust policy로 검증해야 한다. 이 지시서 전달 ZIP의 해시는 외부 전달 기록에 둔다.
