# 커밋 가이드

## 현재 상태

워크플로우 파일이 수정되었습니다:
- ✅ `.github/workflows/deploy.yml` - Docker 빌드 컨텍스트 경로 수정

---

## 커밋 명령어

### 1. 워크플로우 파일만 커밋 (권장)

```bash
# 저장소 루트로 이동
cd "/Users/kwong/Desktop/AI 온디바이스 플랫폼 앱/웹코어자료/tristan050-ai_ondevice_APP"

# 워크플로우 파일만 추가
git add .github/workflows/deploy.yml

# 커밋
git commit -m "fix: Correct Docker build context paths in deploy workflow

- Update context paths to ./webcore_appcore_starter_4_17
- Fix Collector, BFF, and Ops Console build paths
- Resolves workflow failure due to incorrect Dockerfile context"

# 푸시
git push origin main
```

---

### 2. 모든 변경사항 커밋 (선택사항)

다른 파일들도 함께 커밋하려면:

```bash
# 모든 변경사항 추가
git add .

# 커밋
git commit -m "fix: Correct Docker build context paths and update documentation

- Fix deploy workflow Docker build context paths
- Add workflow troubleshooting documentation
- Update deployment guides"

# 푸시
git push origin main
```

---

## 커밋 후 확인

1. **GitHub Actions 확인**:
   - https://github.com/tristan00037-tristan050/tristan050-ai_ondevice_APP/actions
   - 최근 실행 확인
   - 성공 여부 확인

2. **워크플로우 재실행**:
   - Actions 탭 → "Deploy to Production"
   - "Run workflow" 클릭
   - Environment: `staging` 선택
   - "Run workflow" 클릭

---

## 참고

- 워크플로우 파일만 커밋하는 것을 권장합니다 (다른 변경사항과 분리)
- 커밋 메시지는 명확하고 설명적이어야 합니다
- 푸시 후 GitHub Actions에서 자동으로 워크플로우가 실행됩니다


