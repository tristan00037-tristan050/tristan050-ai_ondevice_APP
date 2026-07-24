# Butler FirstScreen v2.3 제품 교정 보고서

이 변경은 별도 하네스나 sidecar 대체물을 만들지 않고 Butler의 실제 UI, Tauri native command,
sidecar CORS, release gate와 공급망 경로를 직접 수정한다.

## 제품 변경

- 위조 가능한 `signature_digest` 검증을 제거했다. 위험 결정은 OpenSSH Ed25519 detached signature,
  단일 allowed-signer principal, 공개키 fingerprint `key_id`, namespace, 유효기간, revocation epoch를
  모두 통과해야 한다. 승인자의 private key나 서명을 개발팀이 대신 만들지 않는다.
- source ZIP verifier가 ZIP entry bytes를 manifest SHA-256/Git blob과 직접 대조한다. 외부·내부
  manifest byte equality, path uniqueness/order, extracted mode, symlink/hardlink/device 차단,
  entry/expanded-size/compression-ratio limit를 강제하고 검증된 archive만 안전 추출한다.
- CycloneDX generator는 `.git`이 없는 source에서 `BUILD_INFO.json`과
  `SOURCE_ARCHIVE_MANIFEST.json`을 공동 authority로 사용하며 두 identity가 다르면 차단한다.
- `Idempotency-Replayed`를 CORS expose header에 추가했다.
- 웹뷰의 `fs:allow-write-file`과 `dialog:allow-save`를 제거했다. 다운로드는 사용자에게 native save
  dialog를 표시한 뒤 같은 native command 안에서 64 MiB 제한·확장자 allowlist·fsync·atomic publish를
  수행한다. 웹 UI는 임의 destination path를 IPC에 전달할 수 없으며 파일 본문은 JSON 확대 없이
  Tauri raw `Uint8Array` IPC로 전달한다.
- generated BFF `dist`가 없는 clean source에서도 policy YAML을 source-level semantic validator로
  검증하도록 repository contract 순서를 정리했다.

## 정직한 완료 경계

로컬 검증은 Python 전체 3,064 pass / 81 baseline fail / 32 skip / collection error 0,
FirstScreen 표적 74 pass / 1 skip, Vitest 335 pass / 0 fail, production web build 2,056 modules다.
v2.2 기준선과 비교한 신규 저장소 회귀 실패는 0건이다. 다만 critical coverage는 combined 68%,
branch 53.18%로 85% gate를 충족하지 못했고, one-command repository contract는 canonical base ref가
없는 복구 저장소에서 `BASE_REF_UNAVAILABLE`로 fail-closed 됐다.

대표 Ed25519 서명·공개키는 아직 제공되지 않았다. 따라서 제목/FTS 평문 예외는 승인되지 않았고
release gate는 의도적으로 BLOCK된다. critical branch coverage 85%, canonical remote/PR/hosted CI,
서명 macOS 앱, Keychain 재시작 연속성, 실제 Playwright/axe/VoiceOver, M3 Metal·memory·thermal·power도
완료 증거가 없다. 이 산출물은 제품 코드 교정본이며 운영 활성화 승인이 아니다.
