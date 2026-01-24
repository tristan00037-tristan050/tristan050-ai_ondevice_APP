# SVR-03 SEALED-ops — SSOT

## 목적
Model Registry Stream(SVR-03)이 운영 단계에서 항상 fail-closed로 유지되도록,
GitHub required checks + 증거 링크를 단일 진실원(SSOT)으로 고정한다.

## 운영 강제(Required checks)
- Branch: main
- Required status checks:
  - product-verify-model-registry

## PR (evidence)
- #164 canonical payload + reason_code v1
  - https://github.com/tristan00037-tristan050/tristan050-ai_ondevice_APP/pull/164
- #165 signature required (fail-closed) for artifact register
  - https://github.com/tristan00037-tristan050/tristan050-ai_ondevice_APP/pull/165
- #166 tamper tests + verify sealing tightened
  - https://github.com/tristan00037-tristan050/tristan050-ai_ondevice_APP/pull/166
- #175 canonicalization 공통화 (P0-5)
  - https://github.com/tristan00037-tristan050/tristan050-ai_ondevice_APP/pull/175
- #176 delivery/apply/rollback 서명 강제 (P0-6)
  - https://github.com/tristan00037-tristan050/tristan050-ai_ondevice_APP/pull/176
- #177 key rotation/revoke (P0-7)
  - https://github.com/tristan00037-tristan050/tristan050-ai_ondevice_APP/pull/177
- #179 영속+감사 (P1-1)
  - https://github.com/tristan00037-tristan050/tristan050-ai_ondevice_APP/pull/179
- #180 저장소 마이그레이션 (P1-2)
  - https://github.com/tristan00037-tristan050/tristan050-ai_ondevice_APP/pull/180
- #181 원자/손상 가드 (P1-3)
  - https://github.com/tristan00037-tristan050/tristan050-ai_ondevice_APP/pull/181
- #182 lock/rotate (P1-4)
  - https://github.com/tristan00037-tristan050/tristan050-ai_ondevice_APP/pull/182
- #183 ops smoke/report (P1-5)
  - https://github.com/tristan00037-tristan050/tristan050-ai_ondevice_APP/pull/183
- #184 batch flush (P1-6)
  - https://github.com/tristan00037-tristan050/tristan050-ai_ondevice_APP/pull/184
- #185 multiproc lock + daily audit (P1-7)
  - https://github.com/tristan00037-tristan050/tristan050-ai_ondevice_APP/pull/185
- #186 ops SSOT 최종화 (P1-8)
  - https://github.com/tristan00037-tristan050/tristan050-ai_ondevice_APP/pull/186

## Actions Run (product-verify-model-registry)
- 최신 run: https://github.com/tristan00037-tristan050/tristan050-ai_ondevice_APP/actions/runs/21238929913

## Ruleset evidence
- docs/ops/evidence/2026-01-23_ruleset_required_checks_svr03_model_registry.md

## Ops policies evidence
- docs/ops/evidence/2026-01-23_svr03_ops_policies.md

## 봉인 커맨드(출력 기반)
- 오염 스캔(0건이어야 함)
  - rg -n "OK=1" webcore_appcore_starter_4_17/backend/model_registry/tests || true

- verify + exit (PASS에서만 키=1, EXIT=0)
  - bash webcore_appcore_starter_4_17/scripts/verify/verify_svr03_model_registry.sh ; echo EXIT=$?

PASS requires:
- MODEL_UPLOAD_SIGN_VERIFY_OK=1
- MODEL_DELIVERY_SIGNATURE_REQUIRED_OK=1
- MODEL_APPLY_FAILCLOSED_OK=1
- MODEL_ROLLBACK_OK=1
- EXIT=0

## 운영 점검 커맨드
- 스모크 테스트 (서명/키/영속/감사 기본 동작 확인)
  - bash webcore_appcore_starter_4_17/scripts/ops/svr03_smoke.sh

- 스토리지 리포트 (data 디렉토리 용량 및 파일 상태)
  - bash webcore_appcore_starter_4_17/scripts/ops/svr03_storage_report.sh

## Audit 정책
- 파일 패턴: `audit_YYYY-MM-DD.json` (일자별)
- 회전 기준: 1MB 초과 시 `audit_YYYY-MM-DD.1.json`으로 회전
- 보관 기간: 최근 14일만 유지 (그 외 자동 삭제)
- 민감 데이터: payload 원문은 절대 저장하지 않음

## Audit 조회 레시피(복붙 커맨드)

공통:
- 기본 출력 상한: 200줄 (LIMIT=200)
- audit 파일: audit_YYYY-MM-DD(.1).json
- 민감 데이터(payload 원문) 저장 금지

1) 특정 날짜 전체(상한 200)
```bash
LIMIT=200 bash webcore_appcore_starter_4_17/scripts/ops/svr03_audit_query.sh --date YYYY-MM-DD
```

2) 기간 조회(from~to)
```bash
LIMIT=200 bash webcore_appcore_starter_4_17/scripts/ops/svr03_audit_query.sh --from YYYY-MM-DD --to YYYY-MM-DD
```

3) reason_code 필터
```bash
LIMIT=200 bash webcore_appcore_starter_4_17/scripts/ops/svr03_audit_query.sh --from YYYY-MM-DD --to YYYY-MM-DD --reason_code <RC>
```

4) key_id 필터
```bash
LIMIT=200 bash webcore_appcore_starter_4_17/scripts/ops/svr03_audit_query.sh --from YYYY-MM-DD --to YYYY-MM-DD --key_id <KEY_ID>
```

5) sha256 필터
```bash
LIMIT=200 bash webcore_appcore_starter_4_17/scripts/ops/svr03_audit_query.sh --from YYYY-MM-DD --to YYYY-MM-DD --artifact_sha256 <SHA256>
```

## Key lifecycle(Active/Grace/Revoked) 운영 커맨드

Ops(메타만 출력, *_OK=1 금지)
```bash
bash webcore_appcore_starter_4_17/scripts/ops/svr03_key_report.sh
```

Verify(출력 키는 verify에서만)
```bash
bash scripts/verify/verify_svr03_key_rotation.sh ; echo EXIT=$?
```

PASS requires:
- KEY_ROTATION_MULTIKEY_VERIFY_OK=1
- KEY_ROTATION_GRACE_PERIOD_OK=1
- KEY_REVOCATION_BLOCK_OK=1
- EXIT=0

## 완료 조건(체크리스트)
- [x] main ruleset/branch protection에서 product-verify-model-registry가 required check로 설정됨
- [x] PR 화면에서 product-verify-model-registry가 필수로 표시되고, 실패 시 머지 불가가 보임
- [x] P0-5~P0-7 PR 링크가 SSOT에 고정됨
- [x] Ruleset evidence 파일이 생성되고 SSOT에 링크됨
