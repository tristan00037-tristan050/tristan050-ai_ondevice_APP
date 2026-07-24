# Butler 첫 화면 제품 통합 v2.1

이 디렉터리는 첫 화면 개편 v2.1의 운영 계약과 검증 범위를 기록한다. 구현 정본은 별도 sidecar나 샘플이 아니라 다음 실제 제품 경로다.

- 저장소·migration·command ledger·turn lifecycle: `butler_pc_core/home/store.py`
- 실제 API: `butler_pc_core/sidecar/routes/home.py`
- capability session·loopback 정책: `butler_pc_core/auth/capability_token.py`, `butler_sidecar.py`
- 실제 첫 화면: `butler-desktop/src/App.tsx`, `butler-desktop/src/components/chat/Sidebar.tsx`
- Tauri app-data/capability bridge: `butler-desktop/src-tauri/src/lib.rs`
- 기계 계약: `contracts/home_v2_1/*.schema.json`
- CI·source·SBOM·provenance: `.github/workflows/firstscreen-v2-1.yml`, `scripts/release/*`

`RUNTIME_ACTIVATION_ALLOWED=0`이다. 로컬 검증, 원격 CI, 서명된 macOS 실기기 검증, 운영 활성화 승인은 서로 다른 게이트이며 자동 승격하지 않는다.

## 단일 정본 원칙

홈의 쓰기는 모두 `HomeStore._command`를 통과하고 같은 SQLite transaction에서 제품 mutation과 replay response를 commit한다. UI는 `/v1/home/*` 제품 endpoint만 사용한다. startup, runtime, durable turn receipt는 `contracts/home_v2_1`의 JSON Schema가 정본이다.

## 현재 검증 경계

로컬 Linux 환경에서 홈 제품/API/schema 테스트, provenance 테스트, 전체 Vitest, TypeScript 및 Vite production build를 실행한다. 저장소 전체 Python suite는 복구한 v1.4 정본에 존재하지 않는 `butler` package, 기존 함수 export 불일치, 미설치 `torch` 때문에 collection 단계에서 닫히지 않는다. 이 상태에서는 `CODE_PASS`, `MERGE_READY`, `PRODUCT_RELEASE_READY`를 참으로 기록하지 않는다.
