# 워크플로우 실패 수정 가이드

## 🔍 현재 상태

GitHub Actions에서 워크플로우가 확인되었습니다:
- ✅ 워크플로우 파일 존재: `.github/workflows/deploy.yml`
- ✅ 워크플로우 실행됨: 1 workflow run
- ❌ **실패 상태**: Failure

**워크플로우 페이지**: https://github.com/tristan00037-tristan050/tristan050-ai_ondevice_APP/actions/workflows/deploy.yml

---

## 🚨 실패 원인 확인

### 1. GitHub에서 로그 확인

1. **워크플로우 실행 페이지로 이동**:
   - https://github.com/tristan00037-tristan050/tristan050-ai_ondevice_APP/actions/runs/[실행-ID]
   - 또는 Actions 탭 → 최근 실행 클릭

2. **실패한 Job 클릭**:
   - "Build and Push Docker Images" 또는 "Deploy to Production"
   - 빨간색 ❌ 표시된 단계 확인

3. **에러 메시지 확인**:
   - 일반적인 원인:
     - Dockerfile 경로 오류
     - 빌드 컨텍스트 경로 오류
     - 의존성 설치 실패
     - 권한 오류

---

## 🔧 일반적인 수정 방법

### 문제 1: Dockerfile 경로 오류

**에러 메시지**: `failed to solve: failed to compute cache key: "/packages/collector-node-ts/Dockerfile" not found`

**원인**: 빌드 컨텍스트와 Dockerfile 경로가 일치하지 않음

**수정**: `deploy.yml` 파일의 경로 확인

```yaml
# 현재 (잘못된 경우)
context: ./webcore_appcore_starter_4_17/packages/collector-node-ts
file: ./webcore_appcore_starter_4_17/packages/collector-node-ts/Dockerfile

# 올바른 경로
context: ./webcore_appcore_starter_4_17
file: ./webcore_appcore_starter_4_17/packages/collector-node-ts/Dockerfile
```

---

### 문제 2: 빌드 컨텍스트 오류

**에러 메시지**: `COPY failed: file not found`

**원인**: 빌드 컨텍스트가 잘못 설정됨

**수정**: 컨텍스트를 프로젝트 루트로 설정

```yaml
context: ./webcore_appcore_starter_4_17
file: ./webcore_appcore_starter_4_17/packages/collector-node-ts/Dockerfile
```

---

### 문제 3: 의존성 설치 실패

**에러 메시지**: `npm ERR!` 또는 `package.json not found`

**원인**: package.json 경로 오류

**수정**: Dockerfile의 COPY 경로 확인

---

## ✅ 빠른 수정 방법

### 방법 1: GitHub에서 직접 확인

1. **실패한 워크플로우 실행 클릭**
2. **에러 메시지 확인**
3. **에러 내용을 기반으로 수정**

### 방법 2: 로컬에서 테스트

```bash
# 저장소 루트로 이동
cd "/Users/kwong/Desktop/AI 온디바이스 플랫폼 앱/웹코어자료/tristan050-ai_ondevice_APP"

# Docker 빌드 테스트
docker build -f webcore_appcore_starter_4_17/packages/collector-node-ts/Dockerfile \
  -t test-collector \
  webcore_appcore_starter_4_17
```

빌드가 실패하면 에러 메시지를 확인하여 수정하세요.

---

## 📋 체크리스트

- [ ] GitHub에서 실패한 워크플로우 실행 로그 확인
- [ ] 에러 메시지 확인
- [ ] Dockerfile 경로 확인
- [ ] 빌드 컨텍스트 경로 확인
- [ ] 로컬에서 Docker 빌드 테스트
- [ ] 수정 후 커밋 및 푸시

---

## 🔗 직접 링크

- **워크플로우 페이지**: https://github.com/tristan00037-tristan050/tristan050-ai_ondevice_APP/actions/workflows/deploy.yml
- **최근 실행**: Actions 탭 → 최근 실행 클릭

---

**다음 단계**: GitHub에서 실패한 워크플로우 실행의 로그를 확인하여 정확한 에러 원인을 파악하세요.


