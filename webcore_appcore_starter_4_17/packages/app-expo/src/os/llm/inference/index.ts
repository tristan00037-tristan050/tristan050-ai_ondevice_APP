import type { InferenceAdapter } from "./types";
import { stubInferenceAdapter } from "./stubAdapter";
import { Platform } from "react-native";
import { WebLLMInferenceAdapter } from "./webllmAdapter";

/**
 * ✅ E06-2: Adapter 선택 로직 (Mock 강제 stub + Platform 분기)
 *
 * 핵심 규칙:
 * - DEMO_MODE=mock → 무조건 stubAdapter (Network 0 강제)
 * - DEMO_MODE=live + LOCAL_LLM_BACKEND=real + Platform=web → WebLLMAdapter
 * - 나머지 → stub (또는 native real 준비 단계)
 */
export function getInferenceAdapter(cfg?: {
  demoMode?: "mock" | "live";
}): InferenceAdapter {
  // ✅ Mock 모드에서는 무조건 stub (Network 0 보장)
  const demoMode =
    cfg?.demoMode ??
    (process.env.EXPO_PUBLIC_DEMO_MODE === "mock" ? "mock" : "live");
  if (demoMode === "mock") {
    return stubInferenceAdapter;
  }

  // Live 모드에서만 Real backend 검토
  const backend = (
    process.env.EXPO_PUBLIC_LOCAL_LLM_BACKEND || "stub"
  ).toLowerCase();
  if (backend === "real" && Platform.OS === "web") {
    return new WebLLMInferenceAdapter();
  }

  // 기본값: stub
  return stubInferenceAdapter;
}
