# GitHub Actions 워크플로우 문제 해결 가이드

## 🔍 워크플로우가 보이지 않는 경우

### 1. 파일 위치 확인

GitHub Actions는 **저장소 루트**의 `.github/workflows/` 디렉토리만 인식합니다.

**확인 방법**:
```bash
# 저장소 루트로 이동
cd "/Users/kwong/Desktop/AI 온디바이스 플랫폼 앱/웹코어자료/tristan050-ai_ondevice_APP"

# 파일 확인
ls -la .github/workflows/
```

**예상 출력**:
```
deploy.yml
ci.yml
backup.yml
```

---

### 2. 파일이 커밋/푸시되었는지 확인

```bash
# Git 상태 확인
git status .github/workflows/

# 커밋되지 않은 파일이 있으면
git add .github/workflows/
git commit -m "fix: Add deployment workflow"
git push origin main
```

---

### 3. YAML 문법 확인

워크플로우 파일에 문법 오류가 있으면 GitHub Actions가 인식하지 못합니다.

**확인 방법**:
1. GitHub 저장소 → **Actions** 탭
2. 오류 메시지 확인 (빨간색 배지)
3. 또는 온라인 YAML 검증 도구 사용

**일반적인 오류**:
- 들여쓰기 오류 (스페이스와 탭 혼용)
- 콜론(`:`) 누락
- 따옴표 불일치

---

### 4. 브랜치 확인

워크플로우 파일이 `main` 브랜치에 있어야 합니다.

```bash
# 현재 브랜치 확인
git branch --show-current

# main 브랜치가 아니면
git checkout main
git push origin main
```

---

### 5. GitHub Actions 활성화 확인

1. GitHub 저장소 → **Settings** → **Actions** → **General**
2. "Allow all actions and reusable workflows" 선택
3. "Save" 클릭

---

### 6. 워크플로우 이름 확인

워크플로우 이름은 파일의 `name:` 필드에서 가져옵니다.

**현재 설정**:
```yaml
name: Deploy to Production
```

**확인 방법**:
- Actions 탭에서 "Deploy to Production" 검색
- 또는 모든 워크플로우 목록 확인

---

## 🚨 즉시 해결 방법

### 방법 1: 파일 재생성

```bash
# 저장소 루트로 이동
cd "/Users/kwong/Desktop/AI 온디바이스 플랫폼 앱/웹코어자료/tristan050-ai_ondevice_APP"

# 기존 파일 삭제 (선택사항)
rm .github/workflows/deploy.yml

# 새로 생성 (간단한 버전)
cat > .github/workflows/deploy.yml << 'EOF'
name: Deploy to Production

on:
  workflow_dispatch:
    inputs:
      environment:
        description: 'Deployment environment'
        required: true
        default: 'staging'
        type: choice
        options:
          - staging
          - production

jobs:
  deploy:
    name: Deploy
    runs-on: ubuntu-latest
    steps:
      - name: Checkout code
        uses: actions/checkout@v4
      
      - name: Echo environment
        run: echo "Deploying to ${{ github.event.inputs.environment }}"
EOF

# 커밋 및 푸시
git add .github/workflows/deploy.yml
git commit -m "fix: Add simple deployment workflow"
git push origin main
```

### 방법 2: GitHub에서 직접 확인

1. GitHub 저장소 → **Code** 탭
2. `.github` → `workflows` → `deploy.yml` 파일 클릭
3. 파일 내용 확인
4. **Raw** 버튼 클릭하여 원본 확인

---

## 📋 체크리스트

- [ ] `.github/workflows/deploy.yml` 파일이 저장소 루트에 있음
- [ ] 파일이 `main` 브랜치에 커밋됨
- [ ] 파일이 GitHub에 푸시됨
- [ ] YAML 문법 오류 없음
- [ ] GitHub Actions가 활성화됨
- [ ] 브랜치가 `main`임

---

## 🔍 디버깅 명령어

```bash
# 1. 파일 존재 확인
ls -la .github/workflows/deploy.yml

# 2. 파일 내용 확인 (첫 10줄)
head -10 .github/workflows/deploy.yml

# 3. Git 상태 확인
git status .github/workflows/

# 4. 최근 커밋 확인
git log --oneline -5 .github/workflows/

# 5. 원격 저장소와 비교
git diff origin/main .github/workflows/deploy.yml
```

---

## 💡 추가 팁

### 워크플로우가 보이지 않는 경우

1. **페이지 새로고침**: F5 또는 Cmd+R
2. **다른 브랜치 확인**: 브랜치 드롭다운에서 `main` 선택
3. **모든 워크플로우 보기**: Actions 탭에서 "All workflows" 클릭
4. **직접 URL 접근**: 
   - `https://github.com/tristan00037-tristan050/tristan050-ai_ondevice_APP/actions`

---

## 📚 참고

- GitHub Actions 문서: https://docs.github.com/en/actions
- YAML 문법: https://yaml.org/

---

**다음 단계**: 위 체크리스트를 확인하고, 문제가 지속되면 GitHub 저장소의 Actions 탭에서 오류 메시지를 확인하세요.


