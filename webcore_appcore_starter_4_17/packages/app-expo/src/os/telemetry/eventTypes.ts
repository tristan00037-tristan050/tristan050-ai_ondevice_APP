export const OS_LLM_USAGE_EVENT_TYPES = [
  // QA/dev 트리거 (환경에서만 사용)
  "qa_trigger_llm_usage",

  // KPI/Audit (메타 only)
  "suggestion_shown",
  "suggestion_used_as_is",
  "suggestion_edited",
  "suggestion_rejected",
  "suggestion_error",
] as const;

export type OsLlmUsageEventType = (typeof OS_LLM_USAGE_EVENT_TYPES)[number];

export function isOsLlmUsageEventType(v: unknown): v is OsLlmUsageEventType {
  return typeof v === "string" && (OS_LLM_USAGE_EVENT_TYPES as readonly string[]).includes(v);
}
