# 첫 화면 저장소 복구 Runbook v2.1

이 절차는 데이터를 자동 복구하거나 새 key로 덮어쓰지 않는다. 사용자가 보는 support code와 digest만 수집하고 원본을 보존한다.

## 공통 절차

1. Butler를 종료하고 중복 프로세스가 없는지 확인한다.
2. `/v1/home/bootstrap-status`의 `status`, `existing_conversation_count`, `support_code`, `tree_oid`만 기록한다.
3. DB, workspace mirror, key 또는 Keychain 항목을 이동·삭제·rename하지 않는다.
4. 개인 경로·대화 제목·메시지 원문·key를 티켓이나 CI 로그에 붙이지 않는다.
5. `integrity` read endpoint와 immutable backup manifest의 digest만 수집한다.

## READ_ONLY_KEY_MISSING / READ_ONLY_KEY_ID_CONFLICT

- 앱과 API를 read-only로 유지하고 model 실행을 금지한다.
- macOS에서는 서명된 앱 identity와 Keychain 접근 상태를 확인한다.
- 새 key 생성, 새 DB 생성, quarantine 또는 backup 삭제를 금지한다.
- 자동 recovery/rekey는 승인된 별도 보안 작업으로 인계한다.

## READ_ONLY_WORKSPACE_MIRROR_MISSING

- DB `home_meta`가 유일한 authority이고 key와 integrity가 정상인지 확인한다.
- 사용자 명시 확인 후 `/v1/home/workspace-mirror/repair` command를 한 번 실행한다.
- command receipt의 request/response digest와 audit event를 확인한다.

## READ_ONLY_WORKSPACE_CONFLICT

- DB와 mirror 중 하나를 자동 선택하지 않는다.
- 양쪽 identifier의 digest만 수집하고 read-only export를 보존한다.
- canonical workspace owner의 승인을 받기 전 repair를 실행하지 않는다.

## READ_ONLY_DB_INTEGRITY_FAILED

- write, migration, model 실행을 금지한다.
- 원본 DB와 모든 backup/manifest를 보존한다.
- `integrity_result=PASS`인 최신 known-good backup을 식별하되 자동 restore하지 않는다.

## MIGRATION_BLOCKED

- legacy source를 삭제하지 않는다.
- conflict item의 ID와 digest만 기록한다.
- 원문 payload를 로그로 전송하지 않는다.
- inventory 변경 시 기존 idempotency key를 재사용하지 않고 승인된 새 migration command를 사용한다.

## 종료 기준

복구 후 재시작하여 `HOME_READY`, 동일 `workspace_id`, 예상 대화 수, message decrypt, audit/command ledger 연속성을 확인한다. 운영 활성화는 별도 승인 대상이다.
