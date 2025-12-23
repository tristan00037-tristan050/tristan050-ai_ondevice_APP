/**
 * R10-S5: On-Device RAG 모듈 진입점
 * 
 * 핵심 원칙:
 * - 데이터는 외부로 안 나감 (온디바이스 임베딩 + 온디바이스 검색)
 * - 게이트웨이 경계 준수
 * - meta-only 텔레메트리 유지
 * - Mock/Live 쌍 유지
 */

export type {
  Embedder,
  VectorStore,
  Retriever,
  ContextBuilder,
  DocumentChunk,
  SearchResult,
  EmbeddingVector,
  RAGConfig,
  RAGMeta,
} from "./types";

export { getEmbedder, StubEmbedder, RealEmbedder } from "./embedder";
export { getVectorStore, StubVectorStore, RealVectorStore } from "./store";
export { RAGRetriever } from "./retriever";
export { RAGContextBuilder } from "./contextBuilder";
export { RAGPipeline, RAGPipelineImpl } from "./pipeline";

/**
 * ✅ R10-S5 P0-4: Hydration 또는 빌드 헬퍼 함수
 */
export async function hydrateOrBuildRAGIndex(
  embedder: Embedder,
  store: VectorStore,
  config: RAGConfig,
  chunks: DocumentChunk[],
  onProgress?: (progress: { progress: number; text: string }) => void
): Promise<{ hydrated: boolean; indexBuildMs?: number; docCount: number }> {
  const pipeline = new RAGPipelineImpl(embedder, store, config);
  return pipeline.hydrateOrBuildIndex(chunks, onProgress);
}

