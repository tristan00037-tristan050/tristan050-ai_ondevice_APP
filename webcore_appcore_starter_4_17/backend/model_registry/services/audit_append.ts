import crypto from "node:crypto";
import { appendAudit } from "./audit";
import type { AuditEventV2 } from "../../../../packages/common/src/audit/audit_event_v2";

function sha256Hex(s: string) {
  return crypto.createHash("sha256").update(s).digest("hex");
}

export function hashActorId(raw: string) {
  // raw 값 자체를 저장하지 않고, 해시만 저장 (meta-only)
  return sha256Hex(raw);
}

export function newEventId(seed: string) {
  // idempotency를 위해 결정적 seed 기반으로도 생성 가능
  return sha256Hex(seed + ":" + Date.now().toString());
}

export function appendAuditV2(evt: AuditEventV2) {
  // audit.ts가 저장하는 event 형태가 AuditEvent였다면, v2를 별도 파일로 저장하는 방식도 가능
  // 여기서는 최소 변경으로 "meta-only" 이벤트를 audit daily 파일에 함께 기록한다고 가정.
  // 민감 데이터 금지 원칙 유지.
  appendAudit({
    ts_ms: Date.parse(evt.ts_utc),
    action: evt.action as any,
    result: evt.outcome,
    reason_code: evt.reason_code,
    key_id: evt.target?.key_id,
    sha256: evt.target?.artifact_sha256,
    // request_id 등은 audit.ts가 확장되면 넣는다
  } as any);
}

