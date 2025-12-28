# R10-S7 ESM Build Anchor "재발 0 잠금" 개발팀 정본 v1.0

> **날짜**: 2025-12-28 기준  
> **상태**: 테스트/보완팀 최종 판정 PASS (재발 0 잠금 완료)

## 1) 목표 정의 (Engineering Contract)

본 잠금의 목표는 단순히 "이번에 PASS"가 아니라, 다음 조건을 구조적으로 강제하는 것입니다.

- **Fail-Closed**: Build Anchor가 유효하지 않으면 서버는 절대 기동되지 않는다 (unknown/빈값/40-hex 미만 생존 경로 0).
- **Single Source of Truth**: 런타임에서 git 계산/추론 금지. 오직 `dist/build_info.json`만 신뢰한다.
- **Deterministic Verification**: 검증은 스크립트가 "결정적으로" 판정한다. FAIL이 한 번이라도 출력되면 즉시 exit 1.
- **Deterministic Destructive Test**: 파괴 테스트는 "가끔 실패"가 아니라 항상 재현 가능한 FAIL이어야 한다.
- **CI Hard Gate**: 위 속성들이 CI에서 "optional"이 아니라 필수 PASS로 강제된다.

## 2) 2025 유효성 근거 (도구/표준 안정성)

- **npm workspace 실행**: `npm run <script> --workspace=<name>` 방식은 npm workspaces 지원 범주에 포함되며 문서화되어 있습니다.
- **ESM 경로 계산**: `import.meta.url`과 `fileURLToPath()` 사용은 Node.js 문서에 의해 정당화됩니다.
- **curl timeout 옵션**: `--connect-timeout`, `--max-time`는 공식 문서에서 timeout 옵션으로 정의되어 있습니다.

## 3) 이미 "PASS로 종결된" 실증 근거 요약

테스트/보완팀 최종 판정은 다음 증빙을 기반으로 PASS입니다.

### prove PASS
- `bash scripts/ops/prove_build_anchor.sh` → exit 0
- proof: `docs/ops/r10-s7-build-anchor-esm-proof-20251227-065612.log`
- .latest → `r10-s7-build-anchor-esm-proof-20251227-065612.log`

### verify PASS
- `BASE_URL="http://127.0.0.1:8081" bash scripts/ops/verify_build_anchor.sh` → exit 0
- 출력: `OK: buildSha matches HEAD(26a635f)`

### 삼각 무결성(결정적) PASS
- HEAD == JSON.buildSha == Header.X-OS-Build-SHA
- 값: `26a635f0dfca0c187b23c6ad9a421a775b228b3c`

### unknown 금지 PASS
- 부트 로그: `[bff] Build anchor loaded successfully`
- unknown/빈값/40자 미만 통과 경로 0

### 커밋/푸시 PASS
- 커밋: `26a635f`
- 메시지: `chore(ops): update latest proof log pointer and clean up duplicate logs`

## 4) 개발팀 하드룰 정본 (위반 시 즉시 FAIL)

### (R0) 루트 고정은 모든 절차의 "첫 줄"
```bash
cd "$(git rev-parse --show-toplevel)/webcore_appcore_starter_4_17"
```

### (R1) 검증/증빙 판정은 scripts/ops/*.sh 만
수동 curl/수동 파이프라인/임의 커맨드로 "PASS 주장" 금지

판정은 오직:
- `scripts/ops/verify_build_anchor.sh`
- `scripts/ops/prove_build_anchor.sh`
- `scripts/ops/destructive_build_anchor_should_fail.sh`

### (R2) ESM 순수성: dist에 require( 재유입 0
패키지 범위 스캔 기준:
```bash
rg -n "require\\(" packages/bff-accounting/dist
```
매치 1건이라도 나오면 즉시 FAIL

### (R3) /healthz buildSha는 fail-closed
unknown/빈값/40-hex 미만은 운영·검증·CI 어디에서도 통과 불가

부트 단계에서 Build Anchor 로드 실패 시 **즉시 종료(process.exit(1))**가 정본

### (R4) 검증 스크립트는 FAIL 1회라도 찍으면 즉시 exit 1
FAIL 출력 후 "계속 진행" 금지

FAIL→PASS 오판을 구조적으로 불가능하게 만든다

### (R5) dev_bff.sh의 /healthz 검사는 "헤더/바디 완전 분리"
- 헤더는 `curl -I` 계열만
- 바디는 `curl` 바디 계열만
- 혼합 스트림 금지 (오판 재발 경로)

### (R6) "파괴 테스트"는 항상 재현 가능한 FAIL (Deterministic Failure)
"부분 확인", "타이밍 이슈", "가끔 실패" 문구는 즉시 Block

파괴 조건 주입 후:
1. 재기동
2. 대기(상한 포함)
3. verify 실행(항상 FAIL 수렴)
을 절차로 고정한다

## 5) 레포에 고정되어야 하는 결정적 구현 사양

### A. BuildInfo 단일 신뢰원천 (런타임 git 계산 금지)
- 런타임은 반드시 `dist/build_info.json`만 읽는다.
- 경로 계산은 ESM에서 `import.meta.url` + `fileURLToPath()`로 고정한다.
- 로딩은 프로세스 전역 캐시(부트 1회)로 고정한다.

검증 규칙:
- `buildSha`: 정규식 `^[0-9a-f]{40}$` 불일치면 throw
- `buildTime`: ISO 파싱 불가/빈값이면 throw

### B. /healthz 단일 매핑 (Header == JSON)
단일 BuildInfo 객체에서
- Header: `X-OS-Build-SHA`, `X-OS-Build-Time`
- JSON: `buildSha`(40), `buildShaShort`(7), `buildTime`(ISO)
를 동시 매핑한다.

## 6) ops 스크립트 "정본" (결정적/재현 가능)

### 6.1 scripts/ops/verify_build_anchor.sh (결정적 판정자)
- bash + set -euo pipefail
- 루트 고정
- 헤더/바디 완전 분리
- Header SHA == JSON SHA == git HEAD
- FAIL 즉시 exit 1
- 성공 출력은 1줄: `OK: buildSha matches HEAD(<short>)`
- BASE_URL 환경변수 지원

### 6.2 scripts/ops/prove_build_anchor.sh (1회 실행: 빌드+기동+검증+증빙+.latest)
- bash + set -euo pipefail + 루트 고정
- 순서 고정: npm ci → workspace build → dev_bff restart → verify → proof log + .latest
- 로그는 "메타만", 상단 80줄 제한
- "하루 최신 1개 유지" 규칙을 절차로 내장(중복 로그 난립 방지)

### 6.3 scripts/ops/destructive_build_anchor_should_fail.sh (파괴 테스트 정본: 항상 재현 가능한 FAIL)
- "타이밍"이 아니라 "절차"로 결정성을 확보
- buildSha를 40-hex이지만 HEAD와 다른 값으로 변조
- 서버는 기동(=dev_bff restart가 정상 경로)
- verify는 항상 FAIL (HEAD 불일치로 수렴)

## 7) CI Hard Gate 정본 (필수 PASS, optional 금지)

CI는 최소 다음을 포함해야 합니다:
1. `npm ci`
2. `npm run build --workspace=@appcore/bff-accounting`
3. `dist/build_info.json` 존재 + 형식 검증(40-hex, ISO)
4. `rg -n "require\(" packages/bff-accounting/dist` → 매치면 FAIL
5. BFF 기동 후 `scripts/ops/verify_build_anchor.sh` 실행(필수)
6. `scripts/ops/destructive_build_anchor_should_fail.sh` 실행(필수, 스크립트 자체는 PASS로 종료)

## 8) npm ci 재발 방지 (결정적 안정화 정본)

### (N1) Node/npm 버전 고정
CI와 로컬의 Node/npm 버전이 어긋나면 npm ci는 lockfile/메타데이터 차이로 쉽게 흔들립니다.

해결: `.nvmrc` / `engines` / CI `setup-node`에서 버전을 고정하여 동일 실행환경을 보장합니다.

### (N2) workspace 스크립트 실행 표준 단일화
workspace 대상 빌드는 항상 `npm run build --workspace=<workspace>`로 고정합니다.

"어떤 디렉토리에서 실행했는지"에 따라 달라지는 절차는 금지합니다(루트 고정으로 차단).

### (N3) workspaces install 스크립트 동시성 리스크 관리
workspaces 환경에서 특정 lifecycle 스크립트가 동시 실행될 수 있으며, 순서 의존성이 있으면 설치/빌드가 비결정적으로 흔들릴 수 있습니다.

해결: install/build 단계에서 순서 의존성이 있는 스크립트는 제거하거나, 필요 시 foreground 실행 정책을 적용하여 결정성을 확보합니다.

## 9) 개발팀 결론(정본)

이번 건은 테스트/보완팀 최종 판정대로 **PASS(재발 0 잠금 완료)**이며, 운영 종결 상태를 정본 문서/스크립트/CI 게이트로 고정했다.

특히 파괴 테스트는 "타이밍 이슈"가 아니라 절차로 결정성을 확보해야 하며, 위 `destructive_build_anchor_should_fail.sh`가 그 정본이다.

앞으로 동일 유형 장애는 사람 실수로 재발 불가능하도록,
- fail-closed,
- 단일 신뢰원천,
- 결정적 verify/prove/destructive,
- CI hard gate
로 잠금 유지한다.

