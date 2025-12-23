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
   * ✅ R10-S5 P0-4: 성능 메타 반환
   */
  index(chunks: DocumentChunk[]): Promise<{ indexBuildMs: number; docCount: number }>;

  /**
   * 쿼리로 관련 문서 검색 및 컨텍스트 생성
   */
  retrieveAndBuildContext(query: string, topK?: number): Promise<{
    context: string;
    results: SearchResult[];
    meta: RAGMeta;
  }>;

  /**
   * ✅ R10-S5 P0-4: Hydration 또는 빌드
   */
  hydrateOrBuildIndex(
    chunks: DocumentChunk[],
    onProgress?: (progress: { progress: number; text: string }) => void
  ): Promise<{ hydrated: boolean; indexBuildMs?: number; docCount: number }>;
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
   * ✅ R10-S5 P0-4: 성능 메타 반환
   */
  async index(chunks: DocumentChunk[]): Promise<{ indexBuildMs: number; docCount: number }> {
    const startTime = Date.now();
    
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
    
    const indexBuildMs = Date.now() - startTime;
    const docCount = (this.store as any).getDocCount?.() || chunks.length;
    
    return { indexBuildMs, docCount };
  }

  /**
   * 쿼리로 관련 문서 검색 및 컨텍스트 생성
   * 
   * ✅ R10-S5 P0-4: 성능 메타 수집 (hydrateMs, docCount 포함)
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
    const storeMeta = this.store.getMeta?.() || {};
    const docCount = (this.store as any).getDocCount?.() || storeMeta.docCount || 0;
    const meta: RAGMeta = {
      ragEnabled: this.config.enabled,
      ragDocs: results.length, // ✅ P0-5: 검색된 문서 수
      ragTopK: topK,
      ragContextChars: context.length,
      ragEmbeddingMs: embedderMeta.embedMs,
      ragRetrieveMs: retrieveMs,
      ragIndexWarm: storeMeta.hydrateMs !== undefined && storeMeta.hydrateMs > 0, // ✅ P0-4: 복원 성공 여부
      ragIndexBuildMs: storeMeta.indexBuildMs,
      ragIndexPersistMs: storeMeta.persistMs,
      ragIndexHydrateMs: storeMeta.hydrateMs,
      ragDocCount: docCount,
    };

    return {
      context,
      results,
      meta,
    };
  }

  /**
   * ✅ R10-S5 P0-4: Hydration 또는 빌드
   * 앱 시작 시 인덱스가 있으면 복원, 없으면 빌드
   */
  async hydrateOrBuildIndex(
    chunks: DocumentChunk[],
    onProgress?: (progress: { progress: number; text: string }) => void
  ): Promise<{ hydrated: boolean; indexBuildMs?: number; docCount: number }> {
    // 1. 스토어 초기화 (복원 시도)
    await this.store.initialize(onProgress);

    // 2. 복원 시도
    const hydrated = await this.store.restore();
    const docCount = (this.store as any).getDocCount?.() || 0;

    if (hydrated && docCount > 0) {
      // Warm start: 복원 성공
      if (onProgress) {
        onProgress({ progress: 100, text: `Index restored: ${docCount} documents` });
      }
      return { hydrated: true, docCount };
    }

    // Cold start: 빌드 필요
    if (onProgress) {
      onProgress({ progress: 0, text: "Building index..." });
    }

    const { indexBuildMs, docCount: newDocCount } = await this.index(chunks);

    if (onProgress) {
      onProgress({ progress: 100, text: `Index built: ${newDocCount} documents` });
    }

    return { hydrated: false, indexBuildMs, docCount: newDocCount };
  }
}

