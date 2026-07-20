# Butler Box5 A4 대사전환 제품 구현 v5 / 계약 v3.2

## 현재 판정

```text
STATUS=IMPLEMENTED_LOCAL_EXTERNAL_GATES_OPEN
CODE_PASS=NO
MERGE_READY=NO
A4_CLOSED=NO
PRODUCT_ACTIVATION_ALLOWED=0
RUNTIME_ACTIVATION_ALLOWED=0
```

판정 정본은 `docs/ops/A4_COMPLETION_STATUS.json`이다. 로컬 제품 경로와 독립 검증
경로가 통과했더라도 운영 finance key, 실제 두 은행 파일, Group A 295, 원격 clean CI,
SLSA provenance, Apple M3 실측이 없으므로 완료나 운영 활성화를 주장하지 않는다.

## 실제 제품 경로 구현

- `butler_sidecar.py`가 분류 업로드의 실제 실행 경계에서 원본을 안전한 snapshot FD로
  고정하고, 비동기 worker 예약 전에 canonical SQLite의 `recon_run`과 `a4_job`을
  `QUEUED`로 commit한다.
- `source_snapshot_v2_1.py`가 `O_NOFOLLOW|O_CLOEXEC`, pre/post `fstat`, SHA-256,
  private copy, unlink, producer/verifier 분리 FD를 사용한다. 지원되지 않는 형식이나
  파일 정체성 변경은 완화하지 않고 차단한다.
- `reconciliation_v2.py`가 실제 은행 행을 canonical transaction으로 컴파일한다.
  회사 소유 계좌는 `bank_code+account_token` 정본 registry에 있어야 하며, 상대 계좌가
  양쪽에서 정확히 검증된 reciprocal pair만 후보가 된다.
- `reconciliation_service_v2.py`가 원자료, 정책, adapter, 사전, registry, code closure를
  한 run에 묶고 evidence staging, 독립 검증, verified publication을 순서대로 수행한다.
  생산자는 검증 권한 공개키와 검증 요청만 사용하고 서명 비밀키나 범용 sign API를 갖지 않는다.
- `verifier_authority.py`가 build-pinned trust와 Unix `SCM_RIGHTS` 원본 FD 전달을 검증한다.
  권한 부재, key substitution, 만료·폐기 epoch, 서명 불일치는 모두 fail-closed다.
- `a4_verifier/cli.py`는 producer 모듈을 import하지 않는 별도 `python -I` 권한 프로세스다.
  보호된 FD로 한 번 주입된 Ed25519 seed는 프로세스 안에서만 보유하고, 전달받은 원자료 FD를
  다시 파싱·컴파일하여 transaction 전체 필드, graph, optimum, DLP, code closure가 모두
  일치할 때만 v3.2 영수증을 서명한다. seed를 반환하는 API는 없다.
- `a4_store_schema_v32.py`는 독립 검증 권한 영수증까지 결속한 단일 상태 머신
  `QUEUED→LEASED→RUNNING→EVIDENCE_STAGED→VERIFYING→VERIFIED→PUBLISHED`를 사용한다.
  검증 전 후보 조회·검토·게시를 DB trigger와 API 양쪽에서 차단하고, 검토 행은 PASS
  verifier receipt에 FK/digest로 결속한다.
- product/channel 원문은 evidence에 기록하지 않고 sealed dictionary ID만 기록한다.
  free string DLP는 base64/hex 중첩 인코딩까지 해제해 계좌·전화·이메일·secret을 막는다.
- 기존 회계 분류 결과, 보고서, journal에는 자동 반영하지 않는다. 모든 A4 결과는
  `affects_reporting=false`, `runtime_activation_allowed=false`다.

## 로컬 검증 범위

- A4 실제 CSV/XLSX raw replay, 독립 권한 프로세스, 저장소 이중 서명검증과 공격 회귀:
  `28 passed`.
- 회계 제품 전체 회귀: `412 passed, 1 skipped`.
- CI `a4-canonical-product`와 동일한 로컬 범위: `430 passed, 1 skipped`.
- 빌드정보·평가 정본 호환 회귀: `71 passed`.
- 정적 검사, Python compile, patch whitespace 검사: PASS.
- 실제 sidecar 앱 E2E, 원격 clean CI, production authority provisioning은 이번 환경에서
  실행하지 않았으며 PASS로 간주하지 않는다.

## 2026 기준과 남은 외부 게이트

- 공급망 종결은 SLSA v1.2 provenance처럼 source, builder, invocation, artifact subject가
  독립 builder에서 결속돼야 한다: https://slsa.dev/spec/v1.2/
- SQLite WAL/transaction commit marker를 전제로 durable queue와 evidence publication을
  한 DB 트랜잭션 경계로 구성했다: https://sqlite.org/fileformat.html
- 성능 완료는 MLPerf Inference v6.0의 재현 가능한 SUT·quality·latency 원칙을 따라야
  한다: https://docs.mlcommons.org/inference/index_gh/
- 실제 두 은행 AB/BA, Group A 295, production verifier authority/Keychain/finance key,
  remote hosted CI,
  signed provenance, full crash/fault matrix, mutation/coverage, Apple M3 성능·전력·thermal
  실측은 아직 실행하지 않았다.

CSV와 XLSX는 독립 raw compiler까지 로컬 검증했다. XLSX의 formula·hidden sheet는
`BLOCK_ADAPTER_POLICY`로 차단한다. 레거시 XLS는 실제 은행 fixture 승인이 없으므로 외부
게이트로 남긴다. 기존 사용자 회계 분류·보고서 경로는 그대로 유지된다.
