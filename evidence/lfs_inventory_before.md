# LFS 정리 전 인벤토리

**날짜**: 2026-04-30  
**브랜치**: `hotfix/remove-lfs-large-files`

---

## LFS 추적 파일 전체 목록

| OID (앞 10자) | 파일 경로 | 크기 | 분류 |
|---------------|-----------|------|------|
| 94b6d38ffa | `packs/micro_default/model.onnx` | 1.5 MB | B — 모델 가중치 |
| 9fb55cfbba | `packs/micro_default/model.onnx.data` | **1.9 GB** | B — 모델 가중치 ← **LFS 한도 초과 원인** |

**총 LFS 크기: 약 1,901.5 MB (≈ 1.9 GB)**

---

## 원인 분석

| 항목 | 내용 |
|------|------|
| LFS 추적 패턴 | `.gitattributes`: `*.onnx`, `*.onnx.data` |
| CI 트리거 | `.github/workflows/windows-ci.yml` — `lfs: true` 설정 |
| 문제 | `windows-ci.yml` 실행마다 `model.onnx.data` (1.9 GB) 다운로드 |
| GitHub LFS 무료 한도 | 1 GB / 월 bandwidth |
| 초과 횟수 | 한 번 실행으로도 한도 초과 (1.9 GB > 1 GB) |

---

## 다른 워크플로우 현황

- 총 35개 워크플로우 중 **34개는 이미 `lfs: false`**
- `windows-ci.yml` 1개만 `lfs: true` → **즉시 수정 대상**

---

## 파일 물리적 위치

```
packs/micro_default/
├── model.onnx       (LFS pointer, 실제 1.5 MB)
└── model.onnx.data  (LFS pointer, 실제 1.9 GB — T7 SSD 또는 Naver Cloud에 보관)
```
