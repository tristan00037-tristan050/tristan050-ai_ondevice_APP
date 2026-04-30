# Windows CI 상태

**최종 변경일**: 2026-04-30  
**현재 상태**: ⏸ **비활성화** (`workflow_dispatch` 수동 실행만 허용)

---

## 비활성화 사유

| 항목 | 내용 |
|------|------|
| **트리거** | PR #646 LFS 정리 시 `packs/micro_default/model.onnx` (1.5 MB) 및 `model.onnx.data` (1.9 GB) git 추적 해제 |
| **영향** | `scripts/ci/windows_cpu_ci_bundle.py` 실행 시 ONNX 모델 파일 미존재 → CI 실패 |
| **우선순위 판단** | 베타 1차 대상이 **macOS 단독** — Windows 복구에 시간 소모는 우선순위 역행 |
| **결정 주체** | 재검토팀 결정: macOS 우선, Windows는 Week 2~4 별도 단계 |

---

## 현재 영향 범위

| 대상 | 상태 |
|------|------|
| macOS CI | ✅ 정상 동작 |
| Day 2~14 작업 | ✅ 영향 없음 |
| 베타 1차 (macOS .dmg) | ✅ 영향 없음 |
| Windows 베타 | ⏸ Week 2~4로 이연 |

---

## 재활성화 조건 (Week 2~4 예정)

### 1단계: ONNX 모델 자산 준비
```bash
# GitHub Releases에 모델 업로드
gh release create model-assets-v1 \
  packs/micro_default/model.onnx \
  packs/micro_default/model.onnx.data \
  --title "Model Assets v1 (ONNX)" \
  --notes "Windows CI용 ONNX 모델 자산"
```

### 2단계: fetch 스크립트 추가
`scripts/ci/fetch_test_fixtures.sh` 에 추가:
```bash
fetch_if_missing \
  "https://github.com/tristan00037-tristan050/tristan050-ai_ondevice_APP/releases/download/model-assets-v1/model.onnx" \
  "packs/micro_default/model.onnx"

fetch_if_missing \
  "https://github.com/tristan00037-tristan050/tristan050-ai_ondevice_APP/releases/download/model-assets-v1/model.onnx.data" \
  "packs/micro_default/model.onnx.data"
```

### 3단계: windows-ci.yml 트리거 복원
```yaml
# .github/workflows/windows-ci.yml 에서 주석 해제:
on:
  push:
    branches: [ "main" ]
  pull_request:
    branches: [ "main" ]
```

### 4단계: Windows CI에 fetch 단계 추가
```yaml
steps:
  - name: Checkout
    uses: actions/checkout@v4
    with:
      lfs: false

  - name: ONNX 모델 다운로드
    run: bash scripts/ci/fetch_test_fixtures.sh
    env:
      FIXTURES_SKIP: "1"  # 캐시 있으면 건너뜀
```

---

## 관련 PR / 커밋

| PR | 내용 |
|----|------|
| #646 | LFS 정리 — model.onnx.data (1.9 GB) 추적 해제 |
| ci/disable-windows-temporarily | Windows CI 트리거 비활성화 (현재 문서) |
