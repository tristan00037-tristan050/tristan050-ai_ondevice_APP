import type { InferenceAdapter } from "./types";
import { Platform } from "react-native";

function isWebGpuAvailable(): boolean {
  if (Platform.OS !== "web") return false;
  return typeof navigator !== "undefined" && !!(navigator as any).gpu;
}

let enginePromise: Promise<any> | null = null;

async function getEngine() {
  if (!enginePromise) {
    const { CreateMLCEngine } = await import("@mlc-ai/web-llm");

    // ⚠️ 중요: 모델 아티팩트 경로는 "동일 오리진 or BFF"로 고정하는 방향이 안전합니다.
    // 여기서는 env로만 받도록 두고, 기본값은 비워서 "설정 없으면 실패"가 더 안전합니다(fail-closed).
    const modelId = process.env.EXPO_PUBLIC_WEBLLM_MODEL_ID;

    if (!modelId) {
      throw new Error("WEBLLM_MODEL_ID_MISSING");
    }

    enginePromise = CreateMLCEngine(modelId, {
      initProgressCallback: (p: any) => {
        // UI를 오염시키지 않기 위해 console로만
        console.log("[webllm] init:", p);
      },
    });
  }
  return enginePromise;
}

export class WebLLMInferenceAdapter implements InferenceAdapter {
  readonly backend = "real" as const;

  async load(): Promise<void> {
    if (!isWebGpuAvailable()) {
      throw new Error("WEBGPU_NOT_AVAILABLE");
    }

    // 모델 로딩은 최초에 다운로드/캐시가 필요하므로, Live에서만 켜고 Mock에서는 절대 켜지 않게 해야 합니다.
    await getEngine();
  }

  async generate(prompt: string, opts?: { maxTokens?: number }): Promise<string> {
    if (!isWebGpuAvailable()) {
      throw new Error("WEBGPU_NOT_AVAILABLE");
    }

    const engine = await getEngine();

    // WebLLM은 OpenAI 스타일 chat API로 생성 호출을 지원합니다.
    const messages = [
      { role: "system", content: "You are a helpful assistant." },
      { role: "user", content: prompt },
    ];

    const reply = await engine.chat.completions.create({
      messages,
      temperature: 0.2,
      max_tokens: opts?.maxTokens ?? 512,
    });

    const text = reply?.choices?.[0]?.message?.content ?? "";
    return text;
  }
}

