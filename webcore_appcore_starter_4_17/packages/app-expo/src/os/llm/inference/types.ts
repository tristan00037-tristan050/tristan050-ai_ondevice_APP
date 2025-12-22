export type InferenceBackend = "stub" | "real";

export interface InferenceLoadProgress {
  progress: number; // 0-100
  text: string; // "Downloading model...", "Loading weights...", etc.
}

export interface InferenceAdapter {
  backend: InferenceBackend;
  load(onProgress?: (progress: InferenceLoadProgress) => void): Promise<void>;
  generate(
    prompt: string,
    opts?: {
      maxTokens?: number;
      onToken?: (token: string) => void; // 스트리밍 토큰 콜백
      signal?: AbortSignal; // 취소 신호
    }
  ): Promise<string>;
}
