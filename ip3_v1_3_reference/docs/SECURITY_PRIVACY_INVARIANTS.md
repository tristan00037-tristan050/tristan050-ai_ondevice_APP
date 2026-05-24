# Security and Privacy Invariants

본 패키지는 telemetry 수집 과정에서 raw prompt, raw user text, raw log, raw hostname, raw IP, raw device id를 저장하지 않습니다.

저장 가능한 값은 다음과 같습니다.

- SHA-256 digest
- CPU/RAM/battery/thermal/network 상태 수치
- CI/VM/physical 여부를 판단하기 위한 비식별화 신호
- collector 및 payload integrity digest

금지되는 값은 다음과 같습니다.

- 사용자의 원문 프롬프트
- 원문 사용자 텍스트
- 원문 로그
- 원문 호스트명
- 원문 IP 주소
- 원문 device id
- 운영 인증정보 또는 secret
