export type InferenceBackend = "stub" | "real";

export interface InferenceAdapter {
  backend: InferenceBackend;
  load(): Promise<void>;
  generate(prompt: string, opts?: { maxTokens?: number }): Promise<string>;
}

