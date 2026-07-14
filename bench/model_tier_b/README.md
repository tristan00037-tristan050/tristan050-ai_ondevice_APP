# Butler 모델티어 B단계 — 알고리즘개발팀12 구현 v2.8.0

첨부된 수정개발지시서 v2.8의 46개 결함, acceptance 90개, attack/mutation 60개를 실행 코드·독립 검증기·테스트·12-job CI 계약으로 구현한 단일 인계본입니다.

## 현재 사실 판정

이 하네스는 실제 저장소(`tristan00037-tristan050/tristan050-ai_ondevice_APP`)의 PR로
적용됐고, 전용 GitHub Actions 워크플로가 raw pytest 로그·JUnit·coverage를 보존하며
green입니다. base full SHA도 확인됐습니다. 제품 어댑터가 실제 Box3/DLP 함수에 도달하고
관측 hook이 off/on byte-동일임을 통합시험으로 증명합니다. 아래 저장소 수준 사실은
갱신하되, **M3 실측·G1은 여전히 BLOCK**이며 `RUNTIME_ACTIVATION_ALLOWED=0`을 유지합니다.

```text
STATUS=HARNESS_APPLIED_CI_GREEN_PRODUCT_ADAPTER_REACHED_M3_BLOCKED
SPEC_REVIEW_PASS=YES
HARNESS_LOCAL_CONTRACT_PASS=YES
BASE_FULL_SHA_RESOLVED=YES
CI_GREEN=YES
CI_RAW_EVIDENCE_RETAINED=YES
ACTUAL_PRODUCT_ADAPTER_PRESENT=YES
ACTUAL_INTEGRATION_TEST_RUNNABLE=YES
ENTRYPOINT_OWNER_BLOB_IN_TREE=YES
SEMANTIC_SUCCESS_PATH_IMPLEMENTED=YES
RELEASE_ARTIFACT_DSSE_BOUND=YES
BENCHMARK_POLICY_COMPLETE=NO
TRUST_POLICY_CONFIGURED=NO
TARGET_M3_PREFLIGHT_PASS=NO
M3_START_ALLOWED=NO
M3_PRODUCT_SAMPLE_COUNT=0
M3_EVIDENCE_PASS=NO
INDEPENDENT_M3_VERIFY_PASS=NO
G1_READY=NO
RUNTIME_ACTIVATION_ALLOWED=0
```

M3 관련 항목(`M3_*`, `G1_READY`, `TARGET_M3_PREFLIGHT_PASS`)이 여전히 `NO`인 것은,
실제 Apple Silicon M3 실측·승인 정책값 확정·서명된 외부 관측 bundle이 이 PR 범위 밖
(머지 후 대표가 직접 수행)이기 때문입니다. 벤치는 측정 도구이며 성능·품질 결론을 내리지
않습니다.

## v2.8 핵심 구현

- duplicate key·float·UNSET·wildcard·만료를 차단하는 canonical JSON 정책
- in-toto Statement subject와 repository/workflow/ref/commit을 결속하는 trust 검증
- inner `release.tar.gz`만 허용하고 outer ZIP 자기서명 주장을 차단하는 attestation 계약
- exact-once `VolatileDraft`와 모든 종료 경로를 통합한 authoritative terminal gate
- tokenizer/config를 포함하는 multi-file 모델 매니페스트, symlink·hardlink·sparse·LFS pointer·pre/post swap 차단
- nonce challenge, 승인 executable provenance, 부모 관측 시각, bounded stdout/stderr, process group 종료를 결속한 worker FSM
- sampler 실행 신원, 8개 mark, PID 집합, gap·누락률, Metal·thermal·LPM·AC 검증
- 서로 다른 모델·PID·동시 상주·양쪽 실제 inference·pre/post digest를 요구하는 dual resident 계약
- mock·존재하지 않는 PID·IPv6/DNS/subprocess escape·활성 구간 공백을 차단하는 OS egress receipt
- receipt 0개, orphan, cycle, duplicate, unknown field를 차단하는 closed evidence DAG
- manifest 밖 파일, 미등록 binary, NUL, UTF-16 secret, archive bomb·traversal·case collision을 검사하는 재귀 scanner
- producer 모듈을 import하지 않는 standalone offline verifier
- 5 epoch, 대표 warmup candidate당 2회, measured AB/BA, candidate·fixture당 10회 일정
- 검증 계측원 없는 joule 추정 금지와 `NOT_MEASURED/NO_DECISION` 계약
- caller boolean을 받지 않고 11개 signed gate receipt를 다시 계산하는 M3 preflight
- 12-job CI와 마지막 signed attestation replay

## 로컬 검증

```bash
chmod +x scripts/*.sh scripts/*.py offline_verifier/verify.py
./scripts/verify_code_package.sh
```

설치·다운로드·네트워크 호출 없이 Python 표준 라이브러리만으로 실행합니다. `offline_verifier/verify.py`의 `code-delivery` 모드는 코드 패키지 무결성만 판정하며 M3 PASS를 주장하지 않습니다. 기본 `m3-evidence` 모드는 필수 receipt가 없으면 반드시 BLOCK합니다.

## 실제 편입 순서

1. 실제 Butler 저장소의 승인 브랜치에서 전체 commit/tree OID와 LFS/submodule 상태를 해소합니다.
2. 제품 모듈에 `butler_bench_run_v2`와 5개 실제 entrypoint observer coverage를 연결합니다.
3. 대표 승인값으로 benchmark/trust/scanner policy를 완성하고 canonical digest를 고정합니다.
4. 실제 1.7B·4B 모델과 fixture/evaluator/runtime 매니페스트를 생성합니다.
5. 12-job CI와 서명 attestation replay를 통과합니다.
6. 승인된 OS deny controller 아래 M3 Max에서 11개 시작 게이트를 검증한 뒤 owner runner를 실행합니다.
7. live semantic verifier와 별도 환경의 offline artifact verifier 결과를 총괄 검토합니다.

## 주요 위치

- `butler_bench/`: producer-side 알고리즘과 fail-closed 계약
- `offline_verifier/verify.py`: producer 비의존 독립 검증기
- `tests/`: 60 attack/mutation과 happy-path 회귀시험
- `schemas/`, `policy/`: closed-world schema 및 승인 전 template
- `spec/v2.8/`: 입력 지시서 정본 전체
- `evidence/local_validation/`: 이번 환경에서 실제 생성한 검증 결과
- `docs/`: 교정 기록, 구현 보고, 실제 제품 인계 절차
