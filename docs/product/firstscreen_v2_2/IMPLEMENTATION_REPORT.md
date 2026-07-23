# Butler FirstScreen v2.2 제품 통합 보고서

이 교정은 별도 sidecar나 검증 전용 제품을 만들지 않고, Butler의 정본 UI·API·저장소·빌드·CI 경로를 직접 변경했다.

## 제품 변경

- 최초 설치는 별도 소유권 marker가 있는 staging 디렉터리에서 완성한 뒤 프로세스 간 install lock, 파일·디렉터리 `fsync`, atomic rename으로 게시한다. 중간 실패는 검증된 Butler 소유 staging만 폐기하며 재시작할 수 있다.
- idempotency 재생 응답의 body는 최초 응답과 byte-equivalent하게 유지하고, 전송 metadata인 `Idempotency-Replayed` header에서 최초와 replay를 구분한다.
- 데스크톱 sidecar 요청은 `http://127.0.0.1:8765`의 정확한 origin과 상대 absolute-path만 허용한다. 외부 origin, credentials, fragment, protocol-relative path, backslash, redirect를 fail-closed 차단한다.
- Tauri CSP에서 `script-src 'unsafe-inline'`을 제거하고 외부 font 요청과 재귀 filesystem scope를 제거했다.
- 삭제 modal은 공용 dialog 계약, cancel initial focus, Tab/Shift+Tab trap, Escape, 호출 menu focus 복귀를 구현했다. 대화 제목과 menu는 키보드 조작 가능한 semantic control로 교정했다.
- source artifact는 Git commit/tree와 각 regular-file Git blob·SHA-256·mode를 결속하고 `.git` 없이 독립 검증한다. `BUILD_INFO.json`은 동일 commit/tree와 commit timestamp에서 결정적으로 생성된다.
- Python dependency는 hash-locked transitive lock으로, Node는 lockfile로, Rust는 toolchain file로 고정했다. CycloneDX 1.6 SBOM은 npm 및 Python resolved component와 dependency edge를 포함한다.
- 저장 위험 결정은 schema, 만료, canonical signature digest를 독립 verifier가 검사한다.

## 검증 판정

프런트엔드 Vitest 331건과 TypeScript/Vite production build, 첫 화면 핵심 Python 43건은 통과했다. `.git` 없는 clean-source의 archive mode·SHA-256·Git blob·Git tree·BUILD_INFO 독립 검증도 통과했고, repo-wide collection error는 6건에서 0건으로 닫혔다. 그러나 저장소 전체는 81건 실패하고 critical branch coverage는 67.34%로 요구치 85%에 미달한다.

브라우저 executable을 이 환경에 정상 설치하지 못해 Playwright/axe 실제 run은 수행하지 않았다. macOS runner, 서명된 `.app`, VoiceOver, Keychain continuity, Apple Silicon M3·Metal 실측, canonical remote/PR/hosted CI/attestation도 실행하지 않았다. 해당 항목은 자동화 정의나 코드 존재만으로 PASS 처리하지 않는다.

현재 제품 변경은 다음 통합·실기기 단계에 투입 가능한 소스 수준이지만, 완료 정의에는 도달하지 않았다. 정본 상태는 `COMPLETION_STATUS.json`이다.
