/**
 * P1-PLAT-01: Trace Event v1 Schema
 * 목적: 이벤트 스키마 정의 및 저장 전 검증 (fail-closed)
 */

import { validateMetaOnlyOrThrow } from "../../../../common/meta_only/validator_v1.cjs";

export interface TraceEventV1 {
  event_id: string;
  request_id: string;
  ts_ms: number;
  kind: "trace_event_v1";
  meta: Record<string, unknown>;
}

const REQUIRED_FIELDS = ["event_id", "request_id", "ts_ms", "kind", "meta"] as const;

/**
 * 저장 전 검증: 필수 필드 확인 + meta-only 검증
 * 실패 시 원문 출력/저장 금지 (짧은 reason_code만)
 */
export function validateTraceEventV1(input: unknown): TraceEventV1 {
  if (input == null || typeof input !== "object") {
    throw new Error("TRACE_EVENT_V1_INVALID: input must be object");
  }

  const obj = input as Record<string, unknown>;

  // 필수 필드 확인
  for (const field of REQUIRED_FIELDS) {
    if (!(field in obj)) {
      throw new Error(`TRACE_EVENT_V1_MISSING_FIELD: ${field}`);
    }
  }

  // kind 검증
  if (obj.kind !== "trace_event_v1") {
    throw new Error(`TRACE_EVENT_V1_INVALID_KIND: expected 'trace_event_v1', got '${obj.kind}'`);
  }

  // event_id, request_id 타입 검증
  if (typeof obj.event_id !== "string" || !obj.event_id) {
    throw new Error("TRACE_EVENT_V1_INVALID: event_id must be non-empty string");
  }
  if (typeof obj.request_id !== "string" || !obj.request_id) {
    throw new Error("TRACE_EVENT_V1_INVALID: request_id must be non-empty string");
  }

  // ts_ms 타입 검증
  if (typeof obj.ts_ms !== "number" || !Number.isFinite(obj.ts_ms)) {
    throw new Error("TRACE_EVENT_V1_INVALID: ts_ms must be finite number");
  }

  // meta 타입 검증
  if (obj.meta == null || typeof obj.meta !== "object" || Array.isArray(obj.meta)) {
    throw new Error("TRACE_EVENT_V1_INVALID: meta must be object");
  }

  // 저장 전 meta-only 검증 (금지 키 차단)
  validateMetaOnlyOrThrow(obj, "trace_event_v1");

  return obj as TraceEventV1;
}

