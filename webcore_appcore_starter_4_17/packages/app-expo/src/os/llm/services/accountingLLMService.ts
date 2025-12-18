import type { DomainLLMService } from "../types";

type AccountingContext = {
  // 원문은 온디바이스에서만 사용(서버 전송 금지)
  hint?: string;
};

export const accountingLLMService: DomainLLMService<AccountingContext> = {
  domain: "accounting",

  buildContext(input: unknown): AccountingContext {
    const any = input as any;
    return { hint: typeof any?.hint === "string" ? any.hint : undefined };
  },

  buildPrompt(ctx: AccountingContext): string {
    return `You are an accounting operator assistant. Hint=${ctx.hint ?? "none"}. Provide a short suggestion.`;
  },

  stubSuggest(ctx: AccountingContext) {
    const suggestionText =
      "승인/내보내기/대사 작업은 순서대로 진행해 주세요. 실패 시 상태 점검(dev_check) 후 재시도하시고, 반복되면 권한/헤더/테넌트 컨텍스트를 먼저 확인해 주세요.";
    return { suggestionText };
  },
};

