export type InferenceBackend = "stub" | "real";

export interface InferenceLoadProgress {
  progress: number; // 0-100
  text: string; // "Downloading model...", "Loading weights...", etc.
}

export interface InferenceAdapter {
  backend: InferenceBackend;
  load(onProgress?: (progress: InferenceLoadProgress) => void): Promise<void>;
  generate(prompt: string, opts?: { maxTokens?: number }): Promise<string>;
}
