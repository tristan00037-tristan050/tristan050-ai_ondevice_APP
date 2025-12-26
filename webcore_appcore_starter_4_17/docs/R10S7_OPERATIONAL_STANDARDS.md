# R10-S7 운영 표준 (Operational Standards)

> **⚠️ 중요**: 이 문서는 "지시서 v3.0의 구현체(Implementation Detail)"입니다.
> 모든 운영 루틴/게이트/PR proof index/리셋 절차는 SSOT로 고정되어 있습니다.

## 0) 운영 SOP (절대 준수 3줄)

1. **수동 절차 금지 → 스크립트로 고정**
2. **완료 = Gate PASS + docs/ops 증빙 + main 재검증 PASS**
3. **meta-only/금지키 유출 0은 Hard Gate**

## 0-1) Build Anchor 운영 표준 (재발 0 잠금)

1. **ESM 런타임에서 require 금지** (런타임 코드에서 발견 시 Block)
2. **/healthz build anchor는 dist/build_info.json 단일 신뢰원천**이며, 런타임 git 조회 금지
3. **build anchor는 unknown/빈값/40자 미만/비-hex이면 즉시 FAIL(exit 1)**
4. **/healthz는 요청마다 파일을 읽지 않고 부트 시 1회 로드 + 캐시만 사용**
5. **dev_bff.sh는 성공 시 `OK: buildSha matches HEAD(<short>)`를 항상 출력**

### 0-1-1) Build Anchor 검증/증빙 (스크립트화, 복붙 블록 금지)

**검증**: 복붙 블록 금지 → 스크립트 실행만 허용
```bash
bash scripts/ops/verify_build_anchor.sh
```

**증빙**: 단일 스크립트로 자동화
```bash
bash scripts/ops/prove_build_anchor.sh
```

증빙 파일:
- `docs/ops/r10-s7-build-anchor-esm-proof-YYYYMMDD-HHMMSS.log`
- `docs/ops/r10-s7-build-anchor-esm-proof.latest` (최신 포인터)

### 0-1-2) Workspace 빌드 표준 (통일)

**팀 표준**: `npm run build --workspace=@appcore/bff-accounting`

모든 스크립트/문서에서 위 형태만 사용 (혼용 금지).

## 1) S6 최종 상태 (SSOT)

### 1-1. 운영 게이트 (항상 PASS 유지)

- `verify_telemetry_rag_meta_only.sh`
- `verify_perf_kpi_meta_only.sh`
- `verify_perf_kpi_regression.sh` (mac-friendly, healthz 기반)
- `verify_ops_proof_manifest.sh`
- `verify_dist_freshness.sh` (2중 앵커: healthz buildSha + src/dist timestamp)

### 1-2. 봉인/무결성 (Seal)

- `docs/ops/r10-s6-seal-manifest.json` (manifestVersion=1)
- `docs/ops/r10-s6-seal-checksums.txt` (self 제외 규칙 유지)
- `docs/ops/r10-s6-seal-checksums.txt.sha256`

### 1-3. 생성/검증

- `generate_s6_seal_artifacts.sh`
- `verify_ops_proof_manifest.sh`
- `verify_golden_master.sh` (범용, manifest 인자화)

## 2) 하드 룰 (재발 방지, 반드시 지킬 것)

### 2-1. main 오염 방지 (증빙 생성 vs 봉인 커밋 분리)

- **main은 기준선 검증용입니다.**
- main에서 proof가 갱신되어 워크트리가 dirty가 되면 **docs PR로만 봉인 커밋**합니다.
- main에 직접 proof 커밋 금지 (발견 시 Block 기준).

### 2-2. 루트/경로 고정 (경로 오류 재발 차단)

```bash
cd "$(git rev-parse --show-toplevel)"
cd "$(git rev-parse --show-toplevel)/webcore_appcore_starter_4_17"
```

### 2-3. BFF는 dist 기반 실행 → dist 신선도 보장 필수 (2중 앵커, fail-closed)

**근본 원인 재발 방지 기준**: src↔dist 불일치는 "추정"이 아니라 게이트 FAIL로 처리합니다.

dist freshness 판정은 아래 2중 앵커를 모두 만족해야 PASS입니다.

## 3) dist freshness gate (필수 강화, 2중 앵커 고정)

### 3-1. 판정 기준 (명문화, FAIL 조건)

`verify_dist_freshness.sh`는 아래 중 하나라도 불만족이면 즉시 FAIL합니다.

**앵커 1 (서버가 실제 무엇을 실행 중인지)**:
- healthz의 buildSha (또는 헤더 X-OS-Build-SHA)가 `git rev-parse HEAD`와 불일치 → FAIL
- 또는 healthz의 buildTime/X-OS-Build-Time이 형식 오류/누락 → FAIL

**앵커 2 (산출물이 최신인지)**:
- dist가 src보다 오래됨 (패키지 단위 또는 지정 경로 단위 비교) → FAIL
- 예: `src/**/*.ts` 최신 수정시각 > `dist/**/*.js` 최신 수정시각이면 FAIL

**결론**: "서버 실행물(healthz)" + "빌드 산출물(dist vs src)" 두 축을 모두 만족해야 PASS입니다.

### 3-2. healthz build anchor는 JSON + 헤더 동시 제공 (권장 → 표준화)

- **JSON 필드**: `buildSha`, `buildTime`
- **응답 헤더**: `X-OS-Build-SHA` (또는 `X-Build-SHA`), `X-OS-Build-Time`
- **이유**: 운영/CI에서 `curl -I`로 즉시 확인 가능 (파싱 불필요).

## 4) verify 출력/캡처 정책 (유출면적 최소화, fail-closed)

### 4-1. 출력 정책 (하드룰)

- verify 실패 시에도 **본문(바디)/json/log 덤프 금지**
- 출력 허용: 경로 / 누락 항목 / 상태코드 / 요약 에러코드만

### 4-2. 캡처 정책 (강화)

- 바디 캡처는 `http_gate.sh` 내부에서만 허용
- 금지키 감지 시 캡처 자체를 중단하고 "금지키 감지로 캡처 스킵"만 기록
- 캡처 파일은 `/tmp/...`에만 저장 (로컬 디버그 전용)
- repo에 자동 커밋 금지
- repo에 남기는 증빙은 **사전에 승인된 경로(docs/ops)**만 허용

## 5) http_gate.sh 의무화 (리뷰 Block 기준 문장 포함)

### 5-1. 의무 규칙

- `verify_*.sh`에서 HTTP 판정/바디 처리/레드액션은 `http_gate.sh`만 사용
- `verify_*.sh` 내부에 `curl` 직접 판정/캡처 구현이 발견되면 **Block**
- 예외는 `http_gate.sh` 내부에서만 허용합니다.

## 6) Golden Master 검증 게이트 (범용화, S6 전용 금지)

### 6-1. 스크립트 설계 (범용)

- `verify_s6_golden_master.sh` 대신 범용 게이트로 설계합니다.
- **표준**: `verify_golden_master.sh --manifest <path>`

**예시**:
```bash
cd webcore_appcore_starter_4_17
bash scripts/verify_golden_master.sh --manifest docs/ops/r10-s6-seal-manifest.json
```

### 6-2. verify_golden_master.sh가 수행할 것 (순서 고정)

1. (비파괴) `generate_s6_seal_artifacts.sh` 실행
2. `verify_ops_proof_manifest.sh` PASS
3. `r10-s6-seal-checksums.txt.sha256` 검증 PASS

## 7) PR 운영 표준 (자동증빙 + 혼입 방지)

### 7-1. PR 코멘트 "필수 4줄" (형식 통일)

아래 4줄은 모든 PR에서 고정합니다.

```
Gate: <script> PASS (cmd: bash scripts/<script>)
Proof: docs/ops/<proof>.latest
Baseline/Seal: docs/ops/r10-s6-seal-manifest.json (manifestVersion=1)
Hard Gate: meta-only/금지키 유출 0 PASS
```

### 7-2. Ops Guard 증빙 코멘트 (필수)

```
[증빙] PR Actions에서 deploy job skipped(배포 0%) 확인 완료. (Run ID: <run_id>)
```

또는

```
[증빙] PR Actions 로그에서 금지 키워드(ssh/rsync/pm2/49.50.139.248//var/www/petad) 0건 확인 완료. (Run ID: <run_id>)
```

### 7-3. PR proof 혼입/오염 방지 (자동 인덱스 생성 필수)

PR에서 `docs/ops` 증빙 파일이 변경되면, 아래를 반드시 수행합니다.

- `scripts/generate_pr_proof_index.sh`로 "이번 PR에서 변경된 docs/ops proof 목록 + 체크섬"을 자동 생성
- PR 코멘트에 그대로 붙여 넣어 "이번 PR이 무엇을 봉인했는지"를 자동 증빙으로 남깁니다.

**사용법**:
```bash
cd webcore_appcore_starter_4_17
bash scripts/generate_pr_proof_index.sh main > pr_proof_index.md
# PR 코멘트에 pr_proof_index.md 내용 붙여넣기
```

## 8) S7 착수 지시 (확정): "품질 개선을 운영화 루프에 편입"

### 8-1. 목표 (정의)

S7은 "기능 추가"가 아니라, retriever 품질 개선을 기존 운영 게이트/증빙 루프에 편입시키는 것입니다.

### 8-2. 브랜치

```bash
git checkout main
git pull --ff-only
git checkout -b feat/r10s7-1-retriever-quality-ops
git push -u origin feat/r10s7-1-retriever-quality-ops
```

### 8-3. 개발 중 상시 PASS (하드룰)

```bash
bash webcore_appcore_starter_4_17/scripts/verify_rag_retrieval.sh
bash webcore_appcore_starter_4_17/scripts/verify_telemetry_rag_meta_only.sh
bash webcore_appcore_starter_4_17/scripts/verify_perf_kpi_regression.sh
bash webcore_appcore_starter_4_17/scripts/verify_ops_proof_manifest.sh
bash webcore_appcore_starter_4_17/scripts/verify_dist_freshness.sh
```

### 8-4. S7 "품질↑ + 성능예산 유지" 수치 KPI 기준 (문서/스크립트 판정으로 고정)

S7에서 논쟁/주관을 없애기 위해 수치 기준을 docs에 박고 스크립트가 자동 FAIL하도록 고정합니다.

**예시 기준 (권장, baseline 대비)**:
- **품질**: `topK_hit_rate ≥ baseline + 0.02` (+2%p)
- **성능**: `p95_inferenceMs ≤ baseline × 1.10` (10% 이내)
- **메모리**: `p95_memoryMB ≤ baseline × 1.15` (15% 이내)

실제 지표 이름은 현재 `verify_rag_retrieval.sh`/`verify_perf_kpi_regression.sh`가 출력하는 JSON 키에 맞춰 SSOT로 고정합니다.

### 8-5. S7 증빙 규칙 (2개 proof 강제)

S7 PR에는 아래 2개 proof를 함께 포함합니다.

1. **Improvement Proof**: 품질 개선 (run json/log)
2. **Non-Regression Proof**: 성능 비회귀 (run json/log)

## 9) 로컬 꼬임/FF-only 실패 복구 표준 (권장 → 준수 규칙)

`git pull --ff-only` 실패 (로컬 diverged/꼬임) 시, 아래 방식만 허용합니다.

- `dev_reset_to_origin_main.sh`를 SOP에 포함
- "FF-only 실패 시 이 스크립트로만 복구"로 규칙화
- **안전 가드**: dirty면 즉시 중단 후 수동 정리 (사고 방지)

**사용법**:
```bash
cd "$(git rev-parse --show-toplevel)"
bash webcore_appcore_starter_4_17/scripts/dev_reset_to_origin_main.sh
```

## 10) 팀 공유용 한 줄 (최종)

S6는 운영 게이트(telemetry/perf meta-only + perf regression loop)와 봉인 체계(manifest v1 + checksums/sha256 + verify gate)까지 main에 고정되어 증빙 기반 Golden Master로 종료되었고, S7은 retriever 품질 개선을 "품질↑ + 성능예산 유지" 수치 KPI와 2중 proof(개선/비회귀)를 기존 운영 게이트/증빙 루프에 편입시키는 방식으로 진행합니다.

