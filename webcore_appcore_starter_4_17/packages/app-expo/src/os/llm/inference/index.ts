import type { InferenceAdapter } from "./types";
import { stubInferenceAdapter } from "./stubAdapter";

export function getInferenceAdapter(): InferenceAdapter {
  const backend = (process.env.EXPO_PUBLIC_LOCAL_LLM_BACKEND || "stub").toLowerCase();
  if (backend === "real") {
    // Real 구현은 다음 단계에서 추가(모델/런타임 확정 후)
    // 현재 스캐폴딩 단계에서는 stub로 폴백
    return stubInferenceAdapter;
  }
  return stubInferenceAdapter;
}

