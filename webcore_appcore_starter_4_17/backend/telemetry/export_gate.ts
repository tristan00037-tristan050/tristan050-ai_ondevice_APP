import crypto from "node:crypto";
import { validateMetaOnly } from "../gateway/guards/meta_only_validator";
import { appendAuditEventV2 } from "./audit_event_v2_append";

type AuditMeta = Record<string, any>;

function writeAuditEventV2(meta: AuditMeta) {
  appendAuditEventV2(meta);
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

