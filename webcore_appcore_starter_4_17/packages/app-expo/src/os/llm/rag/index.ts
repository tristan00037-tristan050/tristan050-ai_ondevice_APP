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

