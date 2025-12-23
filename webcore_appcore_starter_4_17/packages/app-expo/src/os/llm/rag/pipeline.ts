/**
 * R10-S5: RAG 파이프라인 통합
 * 
 * Embedder → VectorStore → Retriever → ContextBuilder end-to-end 실행
 */

import type { DocumentChunk, SearchResult, RAGConfig, RAGMeta } from "./types";
import type { Embedder } from "./types";
import type { VectorStore } from "./types";
import { RAGRetriever } from "./retriever";
import { RAGContextBuilder } from "./contextBuilder";

export interface RAGPipeline {
  /**
   * 문서 인덱싱 (임베딩 + 저장)
   */
  index(chunks: DocumentChunk[]): Promise<void>;

  /**
   * 쿼리로 관련 문서 검색 및 컨텍스트 생성
   */
  retrieveAndBuildContext(query: string, topK?: number): Promise<{
    context: string;
    results: SearchResult[];
    meta: RAGMeta;
  }>;
}

export class RAGPipelineImpl implements RAGPipeline {
  private embedder: Embedder;
  private store: VectorStore;
  private retriever: RAGRetriever;
  private contextBuilder: RAGContextBuilder;
  private config: RAGConfig;

  constructor(
    embedder: Embedder,
    store: VectorStore,
    config: RAGConfig
  ) {
    this.embedder = embedder;
    this.store = store;
    this.config = config;
    this.retriever = new RAGRetriever(embedder, store, config);
    this.contextBuilder = new RAGContextBuilder(config);
  }

  /**
   * 문서 인덱싱
   */
  async index(chunks: DocumentChunk[]): Promise<void> {
    // 1. 임베딩 생성 (배치)
    const texts = chunks.map((chunk) => chunk.text);
    const embeddings = await this.embedder.embedBatch(texts);

    // 2. 임베딩을 청크에 추가
    const chunksWithEmbeddings = chunks.map((chunk, i) => ({
      ...chunk,
      embedding: embeddings[i],
    }));

    // 3. 벡터 스토어에 저장
    await this.store.upsert(chunksWithEmbeddings);
  }

  /**
   * 쿼리로 관련 문서 검색 및 컨텍스트 생성
   */
  async retrieveAndBuildContext(
    query: string,
    topK: number = this.config.topK
  ): Promise<{
    context: string;
    results: SearchResult[];
    meta: RAGMeta;
  }> {
    const startTime = Date.now();

    // 1. 검색
    const results = await this.retriever.retrieve(query, topK);
    const retrieveMs = Date.now() - startTime;

    // 2. 컨텍스트 생성
    const context = this.contextBuilder.buildContext(results);

    // 3. 메타데이터 수집 (텔레메트리용, 원문 금지)
    const embedderMeta = this.embedder.getMeta?.() || {};
    const meta: RAGMeta = {
      ragEnabled: this.config.enabled,
      ragDocs: results.length,
      ragTopK: topK,
      ragContextChars: context.length,
      ragRetrieveMs: retrieveMs,
      ragIndexWarm: false, // TODO: P0-4에서 구현
      ...(embedderMeta.dim && { ragEmbeddingMs: undefined }), // TODO: 임베딩 시간 측정
    };

    return {
      context,
      results,
      meta,
    };
  }
}

