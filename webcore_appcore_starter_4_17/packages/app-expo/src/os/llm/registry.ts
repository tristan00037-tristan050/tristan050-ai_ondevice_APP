import type { DomainId, DomainLLMService } from "./types";
import { csLLMService } from "./services/csLLMService";
import { accountingLLMService } from "./services/accountingLLMService";

const registry: Record<DomainId, DomainLLMService<any, any>> = {
  cs: csLLMService,
  accounting: accountingLLMService,
};

export function isDomainId(v: unknown): v is DomainId {
  return typeof v === "string" && (v === "cs" || v === "accounting");
}

/**
 * fail-closed: 등록되지 않은 도메인은 즉시 에러(조용한 장애 방지)
 */
export function getDomainLLMService(domain: unknown): DomainLLMService<any, any> {
  if (!isDomainId(domain)) {
    const d = typeof domain === "string" ? domain : JSON.stringify(domain);
    const err = new Error(`UNSUPPORTED_DOMAIN:${d}`);
    (err as any).code = "UNSUPPORTED_DOMAIN";
    throw err;
  }
  return registry[domain];
}
