# Day 5 Release Build Evidence

**날짜:** 2026-05-01  
**브랜치:** feature/day5-dmg-release-ux

## 빌드 결과

| 항목 | 값 |
|------|-----|
| 빌드 명령 | `npm run tauri build` (release profile) |
| Rust profile | `[optimized]` (`release`) |
| Rust 컴파일 시간 | 45.51s |
| exit code | 0 (성공) |
| Butler 바이너리 | `src-tauri/target/release/butler-desktop` — **7.9MB** |
| Butler.app | `bundle/macos/Butler.app` — **7.9MB** |
| Butler_0.1.0_aarch64.dmg | `bundle/dmg/Butler_0.1.0_aarch64.dmg` — **3.0MB** |

## DMG 생성 방식

Tauri의 `bundle_dmg.sh` (create-dmg 기반) 가 최종 변환 단계에서 실패  
→ `hdiutil create -format UDZO`로 수동 완성 (`Butler.app` 기준 직접 생성)

```bash
hdiutil create -volname "Butler" \
  -srcfolder <tmpdir with Butler.app + Applications symlink> \
  -ov -format UDZO \
  Butler_0.1.0_aarch64.dmg
```

## 코드 서명 상태

| 항목 | 상태 |
|------|------|
| Apple Developer 등록 | 미가입 |
| 코드 서명 | 없음 (unsigned) |
| 공증 (Notarization) | 없음 |
| Gatekeeper | 최초 실행 시 경고 발생 → 가이드 우회 필요 |

**우회 방법:** `getting_started_v1.md` 1.3절 참조

## 모델 분리 보관

| 항목 | 상태 |
|------|------|
| GGUF 모델 파일 | Butler.app 번들 외부 별도 보관 (T7 SSD) |
| 이유 | LFS 용량 한도 초과 (#646 긴급 수정) |
| 앱 내 경로 | 런타임 시 사용자 지정 모델 경로 참조 |

## Python Sidecar

| 항목 | 상태 |
|------|------|
| `butler_sidecar.py` | `.app` 번들 외부 별도 실행 |
| FastAPI / python-multipart | `requirements-serving.txt` 포함 |
| 로컬 바인딩 | `127.0.0.1:8765` |

## 사전 점검 결과

```
Python 회귀 테스트: 192 PASS / 8 FAIL (기존 문제, Day 5 무관)
  - FAIL 8건: ONNX 변환(LFS 제거), AI 모델 비교 스텁, bundle readiness
Vitest: 24/24 PASS
```

## 향후 빌드 개선 사항

- `create-dmg` CLI 설치 후 Tauri 내장 DMG 스크립트 복구
- Apple Developer Program 가입 후 코드 서명 + 공증 추가
- CI에 macOS release 빌드 단계 추가 (현재 Windows 임시 비활성)
