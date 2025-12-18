import type { DomainLLMService } from "../types";

type CsContext = {
  // 원문은 온디바이스에서만 사용(서버 전송 금지)
  ticketCount: number;
};

export const csLLMService: DomainLLMService<CsContext> = {
  domain: "cs",

  buildContext(input: unknown): CsContext {
    // CS HUD에서 넘기는 구조가 다를 수 있으니, 우선 안전하게 처리합니다.
    const any = input as any;
    const items = Array.isArray(any?.tickets) ? any.tickets : [];
    return { ticketCount: items.length };
  },

  buildPrompt(ctx: CsContext): string {
    // 실모델 붙을 때 사용: 지금은 구조만 고정
    return `You are a CS operator assistant. TicketCount=${ctx.ticketCount}. Provide a short suggestion.`;
  },

  stubSuggest(ctx: CsContext) {
    // Stub(v0): "온디바이스 추론 느낌"만 제공
    const suggestionText =
      ctx.ticketCount === 0
        ? "현재 대기 중인 티켓이 없습니다. 신규 문의 유입 채널을 점검해 주세요."
        : `티켓 ${ctx.ticketCount}건이 있습니다. 우선순위(긴급/환불/장애)를 먼저 분류하고, 표준 답변 템플릿으로 1차 응대를 진행해 주세요.`;

    return { suggestionText };
  },
};

