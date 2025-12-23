/**
 * R10-S5: VectorStore 구현 (Stub)
 * 
 * TODO: 실제 벡터 스토어 구현
 * - 브루트포스/코사인 유사도로 시작
 * - IndexedDB 영속화
 * - Warm start 시 인덱스 복원
 */

import type { VectorStore, DocumentChunk, EmbeddingVector, SearchResult } from "./types";

/**
 * 코사인 유사도 계산
 */
function cosineSimilarity(a: EmbeddingVector, b: EmbeddingVector): number {
  if (a.length !== b.length) return 0;

  let dotProduct = 0;
  let normA = 0;
  let normB = 0;

  for (let i = 0; i < a.length; i++) {
    dotProduct += a[i] * b[i];
    normA += a[i] * a[i];
    normB += b[i] * b[i];
  }

  if (normA === 0 || normB === 0) return 0;
  return dotProduct / (Math.sqrt(normA) * Math.sqrt(normB));
}

/**
 * Stub VectorStore (인메모리)
 */
export class StubVectorStore implements VectorStore {
  private chunks: Array<DocumentChunk & { embedding: EmbeddingVector }> = [];
  private isInitialized = false;
  private indexVersion = "1.0.0";

  async initialize(onProgress?: (progress: { progress: number; text: string }) => void): Promise<void> {
    if (this.isInitialized) return;

    if (onProgress) {
      onProgress({ progress: 0, text: "Initializing vector store..." });
      await new Promise((resolve) => setTimeout(resolve, 100));
      onProgress({ progress: 100, text: "Vector store ready" });
    }

    this.isInitialized = true;
  }

  async upsert(chunks: DocumentChunk[]): Promise<void> {
    // Stub: 임베딩이 없으면 간단한 해시 기반 벡터 생성
    for (const chunk of chunks) {
      if (!chunk.embedding) {
        // 간단한 stub 임베딩 생성
        const embedding: EmbeddingVector = [];
        let hash = 0;
        for (let i = 0; i < chunk.text.length; i++) {
          hash = ((hash << 5) - hash + chunk.text.charCodeAt(i)) & 0xffffffff;
        }
        for (let i = 0; i < 128; i++) {
          const seed = hash + i * 31;
          embedding.push(Math.sin(seed) * 0.5 + 0.5);
        }
        chunk.embedding = embedding;
      }

      // 기존 청크 업데이트 또는 새로 추가
      const existingIndex = this.chunks.findIndex((c) => c.id === chunk.id);
      if (existingIndex >= 0) {
        this.chunks[existingIndex] = { ...chunk, embedding: chunk.embedding! };
      } else {
        this.chunks.push({ ...chunk, embedding: chunk.embedding! });
      }
    }
  }

  async search(queryVector: EmbeddingVector, topK: number): Promise<SearchResult[]> {
    if (this.chunks.length === 0) return [];

    // 브루트포스 코사인 유사도 검색
    const results: SearchResult[] = this.chunks.map((chunk) => ({
      chunk,
      score: cosineSimilarity(queryVector, chunk.embedding),
    }));

    // 점수 내림차순 정렬 및 topK 반환
    return results
      .sort((a, b) => b.score - a.score)
      .slice(0, topK)
      .filter((r) => r.score > 0); // 점수가 0보다 큰 것만
  }

  async persist(): Promise<void> {
    // TODO: IndexedDB에 저장
    // - indexVersion/schemaVersion 관리
    // - 청크 + 임베딩 저장
    console.log("[StubVectorStore] persist() called (not implemented)");
  }

  async restore(): Promise<boolean> {
    // TODO: IndexedDB에서 복원
    // - Warm start 시 인덱스 복원
    // - 실패 시 false 반환 (재빌드 필요)
    console.log("[StubVectorStore] restore() called (not implemented)");
    return false; // Stub에서는 항상 false (재빌드 필요)
  }

  async clear(): Promise<void> {
    this.chunks = [];
    this.isInitialized = false;
  }
}

/**
 * Real VectorStore (TODO: IndexedDB 영속화)
 */
export class RealVectorStore implements VectorStore {
  private isInitialized = false;

  async initialize(onProgress?: (progress: { progress: number; text: string }) => void): Promise<void> {
    // TODO: IndexedDB 초기화
    // - 스키마 버전 확인
    // - Warm start 시 restore() 호출
    throw new Error("RealVectorStore not implemented yet");
  }

  async upsert(chunks: DocumentChunk[]): Promise<void> {
    // TODO: IndexedDB에 저장
    throw new Error("RealVectorStore not implemented yet");
  }

  async search(queryVector: EmbeddingVector, topK: number): Promise<SearchResult[]> {
    // TODO: IndexedDB에서 검색
    throw new Error("RealVectorStore not implemented yet");
  }

  async persist(): Promise<void> {
    // TODO: IndexedDB에 저장
    throw new Error("RealVectorStore not implemented yet");
  }

  async restore(): Promise<boolean> {
    // TODO: IndexedDB에서 복원
    throw new Error("RealVectorStore not implemented yet");
  }

  async clear(): Promise<void> {
    // TODO: IndexedDB 초기화
    throw new Error("RealVectorStore not implemented yet");
  }
}

/**
 * VectorStore 팩토리
 */
export function getVectorStore(demoMode: "mock" | "live"): VectorStore {
  if (demoMode === "mock") {
    return new StubVectorStore();
  }

  // TODO: Live 모드에서 실제 벡터 스토어 사용 여부 결정
  return new StubVectorStore(); // 현재는 stub만
}

