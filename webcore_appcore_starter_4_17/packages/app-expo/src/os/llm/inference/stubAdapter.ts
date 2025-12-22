import type { InferenceAdapter } from "./types";

function sleep(ms: number) {
  return new Promise((r) => setTimeout(r, ms));
}

export const stubInferenceAdapter: InferenceAdapter = {
  backend: "stub",
  async load(onProgress?) {
    // noop (stub은 로딩 없음)
    if (onProgress) {
      onProgress({ progress: 100, text: "Stub mode (no loading required)" });
    }
  },
  async generate(
    prompt: string,
    opts?: {
      maxTokens?: number;
      onToken?: (token: string) => void;
      signal?: AbortSignal;
    }
  ): Promise<string> {
    // 취소 신호 확인
    if (opts?.signal?.aborted) {
      throw new Error("GENERATION_ABORTED");
    }

    // 스트리밍 시뮬레이션 (onToken이 있으면 토큰 단위로 전달)
    const stubText = `요약/추천(Stub): ${prompt.slice(0, 120)}`;
    
    if (opts?.onToken) {
      // 토큰 단위로 나누어 전달 (시뮬레이션)
      const tokens = stubText.split(/(\s+|[^\s]+)/).filter(Boolean);
      for (const token of tokens) {
        if (opts?.signal?.aborted) {
          throw new Error("GENERATION_ABORTED");
        }
        opts.onToken(token);
        await sleep(50); // 토큰 간 지연 시뮬레이션
      }
      return stubText;
    }

    // 비스트리밍: 기존 Stub(v0) 느낌 유지 (지연 + 간단한 응답)
    await sleep(1800);
    return stubText;
  },
};
