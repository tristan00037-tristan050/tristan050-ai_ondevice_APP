# On-Prem Helm Deployment (Phase 2 Enterprise GA)

목적: Kubernetes 클러스터에서 Helm 차트로 온프렘 게이트웨이를 배포한다.

## 0) 전제
- Kubernetes 클러스터 (1.20+)
- Helm 3.x
- kubectl CLI

## 1) Secret 관리

### secrets.enabled=true (기본값)
Chart가 Secret을 생성합니다 (릴리즈 이름 사용).

```yaml
secrets:
  enabled: true
  DATABASE_URL: "postgresql://..."
  EXPORT_SIGN_SECRET: "your-secret-key"
```

### secrets.enabled=false
운영자가 `existingSecretName` Secret을 사전에 만들어야 합니다.

필수 키:
- `DATABASE_URL`
- `EXPORT_SIGN_SECRET`

```yaml
secrets:
  enabled: false
  existingSecretName: "my-existing-secret"
```

주의: `secrets.enabled=false`인데 `existingSecretName`이 비어 있으면 Helm 설치가 실패합니다 (fail-closed).

## 2) 설치

```bash
cd "$(git rev-parse --show-toplevel)/webcore_appcore_starter_4_17/helm/onprem-gateway"
helm install onprem-gateway . -f values.yaml
```

## 3) 상태 확인

```bash
kubectl get pods -l app.kubernetes.io/name=onprem-gateway
kubectl get svc onprem-gateway
```

## 4) 업그레이드

```bash
helm upgrade onprem-gateway . -f values.yaml
```

## 5) 삭제

```bash
helm uninstall onprem-gateway
```

