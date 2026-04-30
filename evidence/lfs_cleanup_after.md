# LFS 정리 후 검증 결과

**날짜**: 2026-04-30  
**브랜치**: `hotfix/remove-lfs-large-files`

---

## 정리 전후 비교

| 항목 | 정리 전 | 정리 후 |
|------|---------|---------|
| LFS 추적 파일 수 | 2개 | **0개** (PR 머지 후) |
| LFS 총 크기 | 1,901.5 MB (≈ 1.9 GB) | **0 MB** |
| `windows-ci.yml` lfs 설정 | `lfs: true` | **`lfs: false`** |
| `.gitattributes` LFS 패턴 | `*.onnx`, `*.onnx.data` | **제거됨** |
| `.gitignore` 모델 패턴 | 일부 누락 | `*.onnx`, `*.onnx.data`, `*.gguf`, `*.bin`, `*.safetensors`, `*.pt`, `*.pth`, `*.ckpt`, `*.mnn`, `*.tflite`, `*.ncnn`, `packs/*/model.*` 추가 |

---

## 수행 작업

| 순서 | 작업 | 명령 |
|------|------|------|
| 1 | LFS 파일 추적 해제 | `git rm --cached packs/micro_default/model.onnx packs/micro_default/model.onnx.data` |
| 2 | .gitattributes LFS 패턴 제거 | LFS 라인 삭제, 주석으로 교체 |
| 3 | .gitignore 강화 | 모델 가중치 패턴 14개 추가 |
| 4 | windows-ci.yml 수정 | `lfs: true` → `lfs: false` |
| 5 | fetch_test_fixtures.sh 작성 | CI용 픽스처 다운로드 스크립트 (현재 빈 상태) |

---

## 회귀 테스트 결과

```
tests/butler_pc_core/ — 23 passed in 0.04s  ✅ 회귀 없음
```

---

## LFS 정리 한계 및 후속 조치

### 이번 PR로 해결되는 것
- **새로운 CI 실행에서 LFS 다운로드 완전 차단** (`lfs: false` + 파일 추적 해제)
- 향후 `.onnx` / `.onnx.data` 파일이 실수로 커밋되지 않음

### 이번 PR로 해결되지 않는 것 (선택적 후속 조치)
- Git history에 남은 LFS 포인터 객체 (기존 커밋에서 참조)
- LFS 스토리지 사용량 감소는 GC 이후 반영

### 선택적 후속 조치 (force-push 필요, 별도 협의)
```bash
# 방법 A: git lfs migrate export (history rewrite)
git lfs migrate export --include="*.onnx,*.onnx.data" --everything
git push --force-with-lease origin main

# 방법 B: BFG Repo-Cleaner (더 안전)
# 1. main 브랜치 백업
git branch backup/before-lfs-cleanup-20260430 origin/main
# 2. BFG 실행
java -jar bfg.jar --strip-blobs-bigger-than 50M
git reflog expire --expire=now --all
git gc --prune=now --aggressive
git push --force-with-lease origin main
```

> ⚠️ force-push는 팀 협의 후 별도 진행. 이번 hotfix로 LFS 초과 문제는 즉시 해결됨.

---

## 파일 물리적 보관 위치

| 파일 | 크기 | 보관 위치 |
|------|------|---------|
| `packs/micro_default/model.onnx` | 1.5 MB | T7 SSD: `/학습모델/` |
| `packs/micro_default/model.onnx.data` | 1.9 GB | T7 SSD: `/학습모델/` |
