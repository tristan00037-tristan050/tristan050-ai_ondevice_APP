# RUNBOOK_EGRESS_DENY_PROOF_V1

EGRESS_DENY_RUNBOOK_V1_TOKEN=1
EGRESS_DENY_PROOF_MUST_RUN_IN_SANDBOX=1
EGRESS_DENY_HOST_PROOF_FORBIDDEN=1

## 규칙
- 증빙은 반드시 deny가 적용되는 환경(Compose 내부 컨테이너 / K8s Pod)에서 수행한다.
- HOST(로컬/러너 호스트)에서 curl로 증빙하는 방법은 금지한다.
- verify 스크립트는 판정만 수행한다(네트워크 시도 금지).

curl localhost:8080

