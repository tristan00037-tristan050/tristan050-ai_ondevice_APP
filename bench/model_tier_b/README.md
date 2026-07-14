# Butler 모델티어 B단계 — 알고리즘개발팀12 구현 v2.8.0

첨부된 수정개발지시서 v2.8의 46개 결함, acceptance 90개, attack/mutation 60개를 실행 코드·독립 검증기·테스트·12-job CI 계약으로 구현한 단일 인계본입니다.

## 현재 사실 판정

```text
STATUS=HARNESS_LOCAL_VALIDATED_PRODUCT_AND_M3_BLOCKED
SPEC_REVIEW_PASS=YES
HARNESS_LOCAL_CONTRACT_PASS=YES
CODE_IMPLEMENTATION_PASS=NO
BASE_FULL_SHA_RESOLVED=NO
BENCHMARK_POLICY_COMPLETE=NO
TRUST_POLICY_CONFIGURED=NO
CI_GREEN=NO
TARGET_M3_PREFLIGHT_PASS=NO
M3_START_ALLOWED=NO
ALL_46_DEFECTS_CLOSED=NO
M3_EVIDENCE_PASS=NO
INDEPENDENT_M3_VERIFY_PASS=NO
G1_READY=NO
RUNTIME_ACTIVATION_ALLOWED=0
```

`CODE_IMPLEMENTATION_PASS=NO`는 로컬 하네스가 없다는 뜻이 아닙니다. 실제 Butler 제품 저장소·전체 Git OID·승인 정책·승인 모델·서명 trust root·12-job CI 원본·M3 Max 실측 자료가 첨부되지 않았으므로, 지시서가 요구하는 제품 통합 완료를 주장하지 않는다는 뜻입니다.

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
