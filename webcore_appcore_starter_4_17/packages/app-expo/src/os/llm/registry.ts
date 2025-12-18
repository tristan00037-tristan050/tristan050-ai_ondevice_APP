import type { DomainId, DomainLLMService } from "./types";
import { csLLMService } from "./services/csLLMService";
import { accountingLLMService } from "./services/accountingLLMService";

const registry: Record<DomainId, DomainLLMService<any, any>> = {
  cs: csLLMService,
  accounting: accountingLLMService,
};

export function getDomainLLMService(domain: DomainId): DomainLLMService<any, any> {
  return registry[domain];
}

