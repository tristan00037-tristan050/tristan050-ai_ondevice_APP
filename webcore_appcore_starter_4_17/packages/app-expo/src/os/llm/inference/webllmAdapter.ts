import type { InferenceAdapter, InferenceLoadProgress } from "./types";
import { Platform } from "react-native";

function isWebGpuAvailable(): boolean {
  if (Platform.OS !== "web") return false;
  return typeof navigator !== "undefined" && !!(navigator as any).gpu;
}

let enginePromise: Promise<any> | null = null;
let loadProgressCallback: ((progress: InferenceLoadProgress) => void) | null =
  null;

async function getEngine(
  onProgress?: (progress: InferenceLoadProgress) => void
) {
  if (!enginePromise) {
    const { CreateMLCEngine } = await import("@mlc-ai/web-llm");

    // ⚠️ 중요: 모델 아티팩트 경로는 "동일 오리진 or BFF"로 고정하는 방향이 안전합니다.
    // 여기서는 env로만 받도록 두고, 기본값은 비워서 "설정 없으면 실패"가 더 안전합니다(fail-closed).
    const modelId = process.env.EXPO_PUBLIC_WEBLLM_MODEL_ID;

    if (!modelId) {
      throw new Error("WEBLLM_MODEL_ID_MISSING");
    }

    // ✅ E06-3: Progress 콜백 저장 (로딩 중 여러 번 호출될 수 있음)
    if (onProgress) {
      loadProgressCallback = onProgress;
    }

    enginePromise = CreateMLCEngine(modelId, {
      initProgressCallback: (p: any) => {
        // ✅ E06-3: Progress를 표준화된 형태로 변환하여 콜백 호출
        if (loadProgressCallback) {
          const progress = typeof p?.progress === "number" ? p.progress : 0;
          const text = p?.text || "Loading model...";
          loadProgressCallback({
            progress: Math.min(100, Math.max(0, progress)),
            text: String(text),
          });
        }
        // 디버깅용 콘솔 로그도 유지
        console.log("[webllm] init:", p);
      },
    });
  }
  return enginePromise;
}

export class WebLLMInferenceAdapter implements InferenceAdapter {
  readonly backend = "real" as const;

  async load(
    onProgress?: (progress: InferenceLoadProgress) => void
  ): Promise<void> {
    if (!isWebGpuAvailable()) {
      throw new Error("WEBGPU_NOT_AVAILABLE");
    }

    // 모델 로딩은 최초에 다운로드/캐시가 필요하므로, Live에서만 켜고 Mock에서는 절대 켜지 않게 해야 합니다.
    await getEngine(onProgress);
  }

  async generate(
    prompt: string,
    opts?: {
      maxTokens?: number;
      onToken?: (token: string) => void;
      signal?: AbortSignal;
    }
  ): Promise<string> {
    if (!isWebGpuAvailable()) {
      throw new Error("WEBGPU_NOT_AVAILABLE");
    }

    const engine = await getEngine();

    // WebLLM은 OpenAI 스타일 chat API로 생성 호출을 지원합니다.
    const messages = [
      { role: "system", content: "You are a helpful assistant." },
      { role: "user", content: prompt },
    ];

    // 스트리밍 지원 확인 및 처리
    const createOptions: any = {
      messages,
      temperature: 0.2,
      max_tokens: opts?.maxTokens ?? 512,
    };

    // WebLLM 스트리밍 지원 여부 확인
    let accumulatedText = "";
    let isStreaming = false;

    try {
      // stream 옵션이 있으면 스트리밍 시도
      if (opts?.onToken) {
        createOptions.stream = true;
        isStreaming = true;
      }

      const reply = await engine.chat.completions.create(createOptions);

      // 스트리밍 응답 처리
      if (isStreaming && reply && typeof (reply as any)[Symbol.asyncIterator] === "function") {
        // AsyncIterable 스트림 처리
        for await (const chunk of reply as any) {
          // 취소 신호 확인
          if (opts?.signal?.aborted) {
            throw new Error("GENERATION_ABORTED");
          }

          const delta = chunk?.choices?.[0]?.delta?.content;
          if (delta) {
            accumulatedText += delta;
            opts.onToken?.(delta);
          }
        }
        return accumulatedText;
      }

      // 비스트리밍 응답 (기존 방식)
      const text = reply?.choices?.[0]?.message?.content ?? "";
      return text;
    } catch (error: any) {
      // 취소 신호 확인
      if (opts?.signal?.aborted || error?.message === "GENERATION_ABORTED") {
        throw new Error("GENERATION_ABORTED");
      }
      throw error;
    }
  }
}
