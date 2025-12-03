# GitHub 푸시 가이드

Phase 5.4 릴리스 패키지 및 배포 워크플로우를 GitHub에 푸시하는 방법입니다.

## 🚀 빠른 시작

### 1. 현재 상태 확인

```bash
# 변경된 파일 확인
git status

# 원격 저장소 확인
git remote -v
```

---

## 📋 푸시 절차

### 단계 1: 변경사항 확인

```bash
cd webcore_appcore_starter_4_17
git status
```

**예상 출력**: 다음 파일들이 표시되어야 합니다:
- `.github/workflows/deploy.yml` (새로 생성 또는 수정)
- `docs/GITHUB_ACTIONS_SETUP.md` (새로 생성)
- `docs/DEPLOYMENT_OPTIONS.md` (새로 생성)
- `docs/GO_LIVE_EXECUTION_PLAN.md` (새로 생성)
- `docs/KUBERNETES_SETUP.md` (새로 생성)
- `docs/QUICK_START_K8S.md` (새로 생성)
- `scripts/setup-k8s.sh` (새로 생성)
- `config/collector.env.sample` (새로 생성)
- `config/ops-console.env.sample` (새로 생성)
- 기타 Phase 5.4 관련 파일들

---

### 단계 2: 파일 추가

```bash
# 모든 변경사항 추가
git add .

# 또는 특정 파일만 추가
git add .github/workflows/deploy.yml
git add docs/
git add scripts/
git add config/
```

---

### 단계 3: 커밋

```bash
git commit -m "feat: Add Phase 5.4 release package and deployment workflow

- Add production deployment workflow (GitHub Actions)
- Add release documentation (RELEASE_NOTES_5_4.md, GO_LIVE_CHECKLIST.md, etc.)
- Add Kubernetes setup scripts and guides
- Add CI security checks (roles guard, client filter)
- Add smoke test script
- Add environment variable samples
- Update CI pipeline with security checks"
```

---

### 단계 4: 푸시

```bash
# 현재 브랜치 확인
git branch

# main 브랜치로 푸시
git push origin main

# 또는 다른 브랜치인 경우
git push origin <branch-name>
```

---

## 🔍 푸시 후 확인

### 1. GitHub 저장소에서 확인

1. GitHub 저장소 페이지로 이동
2. **Actions** 탭 클릭
3. 왼쪽 사이드바에서 **"Deploy to Production"** 워크플로우 확인

**워크플로우가 보이지 않으면**:
- 페이지 새로고침 (F5 또는 Cmd+R)
- 브랜치가 `main`인지 확인
- `.github/workflows/deploy.yml` 파일이 저장소에 있는지 확인:
  - 저장소 → `.github` → `workflows` → `deploy.yml`

---

### 2. 파일 확인

GitHub 저장소에서 다음 파일들이 있는지 확인:

**워크플로우**:
- `.github/workflows/deploy.yml`
- `.github/workflows/ci.yml` (업데이트됨)

**문서**:
- `docs/RELEASE_NOTES_5_4.md`
- `docs/GO_LIVE_CHECKLIST.md`
- `docs/ROLLBACK_PLAN.md`
- `docs/OBSERVABILITY_DASHBOARD_NOTES.md`
- `docs/SECURITY_AUDIT_CHECKLIST.md`
- `docs/GITHUB_ACTIONS_SETUP.md`
- `docs/DEPLOYMENT_OPTIONS.md`
- `docs/GO_LIVE_EXECUTION_PLAN.md`
- `docs/KUBERNETES_SETUP.md`
- `docs/QUICK_START_K8S.md`

**스크립트**:
- `scripts/smoke.sh`
- `scripts/check_roles_guard.mjs`
- `scripts/check_client_filter.mjs`
- `scripts/setup-k8s.sh`

**설정**:
- `config/collector.env.sample`
- `config/ops-console.env.sample`

---

## ⚠️ 문제 해결

### 문제: "remote: Permission denied"

**원인**: GitHub 인증 실패

**해결**:
1. SSH 키 확인:
   ```bash
   ssh -T git@github.com
   ```
2. 또는 Personal Access Token 사용:
   ```bash
   git remote set-url origin https://<token>@github.com/<user>/<repo>.git
   ```

---

### 문제: "branch is behind"

**원인**: 원격 저장소에 새로운 커밋이 있음

**해결**:
```bash
# 원격 변경사항 가져오기
git fetch origin

# 병합
git merge origin/main

# 또는 리베이스
git rebase origin/main

# 다시 푸시
git push origin main
```

---

### 문제: "workflow file is invalid"

**원인**: YAML 파일 문법 오류

**해결**:
1. YAML 문법 확인:
   ```bash
   # YAML 검증 도구 사용 (선택사항)
   yamllint .github/workflows/deploy.yml
   ```
2. GitHub Actions 탭에서 오류 메시지 확인
3. 파일 수정 후 다시 커밋/푸시

---

## 📝 체크리스트

푸시 전:
- [ ] `git status`로 변경사항 확인
- [ ] 커밋 메시지 작성
- [ ] 원격 저장소 확인 (`git remote -v`)

푸시 후:
- [ ] GitHub 저장소에서 파일 확인
- [ ] Actions 탭에서 워크플로우 확인
- [ ] 워크플로우 파일 내용 확인 (`.github/workflows/deploy.yml`)

---

## 🎯 다음 단계

파일이 GitHub에 푸시되면:

1. **GitHub Secrets 설정**
   - Settings → Secrets and variables → Actions
   - `docs/GITHUB_ACTIONS_SETUP.md` 참고

2. **워크플로우 테스트**
   - Actions 탭 → "Deploy to Production" → "Run workflow"

3. **배포 실행**
   - `docs/GO_LIVE_EXECUTION_PLAN.md` 참고

---

## 📚 참고 문서

- `docs/GITHUB_ACTIONS_SETUP.md` - GitHub Actions 설정 가이드
- `docs/DEPLOYMENT_OPTIONS.md` - 배포 옵션 가이드
- `docs/GO_LIVE_EXECUTION_PLAN.md` - Go-Live 실행 계획

---

**중요**: 파일을 GitHub에 푸시한 후에만 Actions 탭에서 워크플로우를 볼 수 있습니다!


