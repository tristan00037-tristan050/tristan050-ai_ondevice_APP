# RUNBOOK: release-bff Phase 1/2 (ondevice)

## Phase 1 (현재 SSOT)
목표: 배포 대상이 로컬 minikube(127.0.0.1)인 상황에서, deploy는 self-hosted 러너에서만 수행한다.

필수 조건 3개(하나라도 깨지면 BLOCK)
1) publish-and-deploy job은 self-hosted(macOS/ARM64)에서 실행
2) self-hosted 머신에서 minikube/k8s 도달 가능 (kubectl cluster-info 성공)
3) 배포가 보는 kubeconfig는 로컬 ~/.kube/config이며,
   - context=minikube로 핀
   - cluster.server가 127.0.0.1/localhost인지 강제 확인

대표 함정 4개
- publish-and-deploy가 ubuntu-latest로 돌아감: 로컬 minikube 접근 불가(무조건 실패)
- minikube가 꺼짐: connection refused/timeout 반복
- 컨텍스트가 minikube가 아님: 엉뚱한 클러스터로 배포될 위험
- kubeconfig를 Secrets로 넣어 해결 시도: server=127.0.0.1이면 외부 러너에서는 무조건 실패

실행(증빙)
- 머지 후 반드시 "새 태그"로 실행(run) 생성
- 기존 태그 재사용/덮어쓰기 금지
