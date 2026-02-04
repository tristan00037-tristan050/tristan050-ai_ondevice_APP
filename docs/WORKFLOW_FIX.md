# GitHub Actions 워크플로우 수정 가이드

## 🔍 문제 원인

GitHub Actions는 **저장소 루트**의 `.github/workflows/` 디렉토리만 인식합니다.

현재 상황:
- ❌ 워크플로우 파일이 `webcore_appcore_starter_4_17/.github/workflows/`에 있음
- ✅ 워크플로우 파일이 저장소 루트 `.github/workflows/`에 있어야 함

---

## ✅ 해결 방법

### 1. 저장소 루트로 이동

```bash
cd "/Users/kwong/Desktop/AI 온디바이스 플랫폼 앱/웹코어자료/tristan050-ai_ondevice_APP"
```

### 2. 워크플로우 파일 확인

```bash
# 저장소 루트의 .github/workflows/ 확인
ls -la .github/workflows/

# 예상 출력:
# deploy.yml
# ci.yml
# backup.yml
```

### 3. 파일이 없으면 복사

```bash
# .github/workflows/ 디렉토리 생성 (없는 경우)
mkdir -p .github/workflows

# 워크플로우 파일 복사
cp webcore_appcore_starter_4_17/.github/workflows/deploy.yml .github/workflows/deploy.yml
cp webcore_appcore_starter_4_17/.github/workflows/ci.yml .github/workflows/ci.yml
cp webcore_appcore_starter_4_17/.github/workflows/backup.yml .github/workflows/backup.yml
```

### 4. 경로 수정 (중요!)

`deploy.yml` 파일의 경로를 수정해야 합니다:

**변경 전**:
```yaml
context: ./packages/collector-node-ts
file: ./packages/collector-node-ts/Dockerfile
```

**변경 후**:
```yaml
context: ./webcore_appcore_starter_4_17/packages/collector-node-ts
file: ./webcore_appcore_starter_4_17/packages/collector-node-ts/Dockerfile
```

### 5. 커밋 및 푸시

```bash
# 변경사항 확인
git status

# 파일 추가
git add .github/workflows/

# 커밋
git commit -m "fix: Move workflows to repository root for GitHub Actions"

# 푸시
git push origin main
```

---

## 🔍 확인 방법

### GitHub에서 확인

1. https://github.com/tristan00037-tristan050/tristan050-ai_ondevice_APP 로 이동
2. **Code** 탭 → `.github` → `workflows` → `deploy.yml` 파일 확인
3. **Actions** 탭 클릭
4. 왼쪽 사이드바에서 **"Deploy to Production"** 워크플로우 확인

**워크플로우가 보이지 않으면**:
- 페이지 새로고침 (F5 또는 Cmd+R)
- 브랜치가 `main`인지 확인
- 파일 경로 확인: `.github/workflows/deploy.yml` (루트에 있어야 함)

---

## 📋 체크리스트

- [ ] 저장소 루트에 `.github/workflows/` 디렉토리 존재
- [ ] `deploy.yml` 파일이 루트의 `.github/workflows/`에 있음
- [ ] 파일 내 경로가 `webcore_appcore_starter_4_17/`로 수정됨
- [ ] GitHub에 커밋 및 푸시 완료
- [ ] Actions 탭에서 워크플로우 확인

---

## 🚨 주의사항

- GitHub Actions는 저장소 루트의 `.github/workflows/`만 인식합니다
- 서브디렉토리의 `.github/workflows/`는 무시됩니다
- 워크플로우 파일 내 경로도 저장소 루트 기준으로 수정해야 합니다

---

**다음 단계**: 파일을 저장소 루트로 이동하고 푸시한 후, Actions 탭에서 워크플로우를 확인하세요!


