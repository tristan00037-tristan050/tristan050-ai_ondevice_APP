import type { InferenceAdapter } from "./types";

function sleep(ms: number) {
  return new Promise((r) => setTimeout(r, ms));
}

export const stubInferenceAdapter: InferenceAdapter = {
  backend: "stub",
  async load() {
    // noop
  },
  async generate(prompt: string) {
    // 기존 Stub(v0) 느낌 유지 (지연 + 간단한 응답)
    await sleep(1800);
    return `요약/추천(Stub): ${prompt.slice(0, 120)}`;
  },
};

