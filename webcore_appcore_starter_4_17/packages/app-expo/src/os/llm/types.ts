export type DomainId = "cs" | "accounting";

export interface DomainLLMService<TContext = unknown, TResponse = unknown> {
  domain: DomainId;

  // 온디바이스 컨텍스트 구성(원문 포함 가능: HUD 내부 메모리)
  buildContext(input: unknown): TContext;

  // 실모델 전환 시 사용할 프롬프트(온디바이스)
  buildPrompt(ctx: TContext): string;

  // Stub(v0) 단계에서는 이 함수로 추천문을 만든다(온디바이스)
  stubSuggest(ctx: TContext): { suggestionText: string };
}

