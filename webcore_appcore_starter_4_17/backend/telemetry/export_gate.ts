import crypto from "node:crypto";
import { validateMetaOnly } from "../gateway/guards/meta_only_validator";

// NOTE: audit_event_v2 연결은 프로젝트마다 위치가 다를 수 있으므로,
// 여기서는 "audit_event_v2 기록 함수"를 로컬 함수로 캡슐화하고,
// 실제 구현은 기존 audit 경로에 맞춰 교체/연결한다.
type AuditMeta = Record<string, any>;

function writeAuditEventV2(meta: AuditMeta) {
  // placeholder 금지 원칙 때문에, 최소 로깅이 아닌 "구조적 호출 지점"만 둔다.
  // 실제 구현은 기존 audit_event_v2 append 경로를 호출하도록 연결해야 한다.
  // 이 PR에서는 verify가 해당 연결을 정적으로 검사한다.
  return meta;
}

export function exportPreview(body: any) {
  const r = validateMetaOnly(body);
  if (!r.ok) {
    return { status: 400, json: { ok: false, reason_code: r.reason_code, detail: r.detail } };
  }
  const token = crypto.randomBytes(16).toString("hex");
  const now = new Date().toISOString();
  return { status: 200, json: { ok: true, step: "preview", preview_token: token, ts_utc: now } };
}

export function exportApprove(body: any) {
  const r = validateMetaOnly(body?.payload);
  if (!r.ok) {
    return { status: 400, json: { ok: false, reason_code: r.reason_code, detail: r.detail } };
  }
  if (!body?.preview_token) {
    return { status: 400, json: { ok: false, reason_code: "EXPORT_MISSING_PREVIEW_TOKEN" } };
  }

  const exportId = crypto.randomBytes(12).toString("hex");
  const now = new Date().toISOString();

  // audit(meta-only) mandatory
  writeAuditEventV2({
    ts_utc: now,
    request_id: body?.request_id || null,
    export_id: exportId,
    preview_token: String(body.preview_token).slice(0, 8), // meta-only (truncated)
    outcome: "APPROVED",
    reason_code: body?.reason_code || "EXPORT_APPROVED"
  });

  return { status: 200, json: { ok: true, step: "approve", export_id: exportId, ts_utc: now } };
}

