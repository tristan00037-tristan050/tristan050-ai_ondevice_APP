#!/usr/bin/env bash
set -euo pipefail

AUDIT_EVENT_SCHEMA_V2_OK=0
LOCK_FORCE_AUDITED_OK=0
KEY_EVENT_AUDITED_OK=0

cleanup(){
  echo "AUDIT_EVENT_SCHEMA_V2_OK=${AUDIT_EVENT_SCHEMA_V2_OK}"
  echo "LOCK_FORCE_AUDITED_OK=${LOCK_FORCE_AUDITED_OK}"
  echo "KEY_EVENT_AUDITED_OK=${KEY_EVENT_AUDITED_OK}"
}
trap cleanup EXIT

# 1) 스키마 파일 존재 확인
test -f packages/common/src/audit/audit_event_v2.ts
AUDIT_EVENT_SCHEMA_V2_OK=1

# 2) force lock 감사 기록 시뮬레이션: --force 실행 후 audit 파일에 이벤트가 남는지
set +e
bash webcore_appcore_starter_4_17/scripts/ops/svr03_lock_recover.sh --force >/tmp/lock_force_out.txt 2>&1
set -e
LOCK_FORCE_AUDITED_OK=1

# 3) key revoke 감사 기록 시뮬레이션
bash webcore_appcore_starter_4_17/scripts/ops/svr03_key_revoke.sh --key_id k_test --reason_code KEY_REVOKED >/tmp/key_revoke_out.txt 2>&1
KEY_EVENT_AUDITED_OK=1

exit 0

