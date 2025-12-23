/**
 * R10-S5: Retriever 구현
 * 
 * 쿼리에서 관련 문서 청크 검색
 */

import type { Retriever, SearchResult, RAGConfig } from "./types";
import type { Embedder } from "./types";
import type { VectorStore } from "./types";

export class RAGRetriever implements Retriever {
  constructor(
    private embedder: Embedder,
    private store: VectorStore,
    private config: RAGConfig
  ) {}

  async retrieve(query: string, topK: number = this.config.topK): Promise<SearchResult[]> {
    // 1. 쿼리를 임베딩 벡터로 변환
    const queryVector = await this.embedder.embed(query);

    // 2. 벡터 스토어에서 검색
    const results = await this.store.search(queryVector, topK);

    // 3. 최소 점수 필터링 (설정된 경우)
    if (this.config.minScore !== undefined) {
      return results.filter((r) => r.score >= this.config.minScore!);
    }

    return results;
  }
}

