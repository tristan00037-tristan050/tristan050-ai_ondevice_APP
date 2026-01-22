# SVR-03 Signing Canonical Payload v1

## 목적
- 모델 레지스트리(SVR-03)에서 "서명 검증"이 환경/언어/런타임 차이로 흔들리지 않도록, 서명 대상 payload의 canonical(정규) 직렬화 규칙을 고정한다.
- 테스트/검증 스크립트/서버 구현이 동일한 입력을 만들어 같은 서명 결과를 얻는 것을 목표로 한다.

## Canonical JSON 규칙
- 인코딩: UTF-8
- 공백/줄바꿈: 최소 JSON(불필요한 공백 금지)
- 키 정렬: 객체 key는 유니코드 코드포인트 오름차순(lexicographic)
- 배열: 입력 순서 유지(정렬 금지)
- 숫자: 가능하면 정수/고정소수 사용(지수 표기 금지 권장)

## 공통 필드(필수)
- v: "v1"
- ts_ms: number (epoch ms)
- tenant_id: string
- op: string
- body: object

## op 값(v1)
- ARTIFACT_REGISTER
- DELIVERY_APPLY
- DELIVERY_ROLLBACK

## body 스키마(v1)

### 1) ARTIFACT_REGISTER
- model_id, version_id, platform, runtime, sha256, size_bytes, storage_ref

### 2) DELIVERY_APPLY
- model_id, version_id, artifact_id
- target: { device_class, min_app_version }

### 3) DELIVERY_ROLLBACK
- model_id, version_id, artifact_id
- reason_code (SVR03_REASON_CODES_V1.md 참조)

## 서명 필드(권장)
- signature: base64
- sig_alg: "ed25519" 또는 "hmac-sha256"
- key_id: 키 로테이션 대비

## Fail-Closed
- signature 누락/불일치: 즉시 4xx + reason_code
- 거절된 요청은 저장/적용 0

