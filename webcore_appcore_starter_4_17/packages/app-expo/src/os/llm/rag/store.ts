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
 * IndexedDB 헬퍼 (웹 환경 전용)
 */
function isIndexedDBAvailable(): boolean {
  return typeof window !== "undefined" && "indexedDB" in window;
}

function openDB(): Promise<IDBDatabase> {
  return new Promise((resolve, reject) => {
    if (!isIndexedDBAvailable()) {
      reject(new Error("IndexedDB not available"));
      return;
    }

    const request = indexedDB.open("rag_vector_store", 1);

    request.onerror = () => reject(request.error);
    request.onsuccess = () => resolve(request.result);

    request.onupgradeneeded = (event) => {
      const db = (event.target as IDBOpenDBRequest).result;
      if (!db.objectStoreNames.contains("chunks")) {
        const store = db.createObjectStore("chunks", { keyPath: "id" });
        store.createIndex("sourceId", "metadata.sourceId", { unique: false });
      }
    };
  });
}

/**
 * Real VectorStore (IndexedDB 영속화)
 * 
 * ✅ R10-S5 P0-4: IndexedDB 기반 영속화
 * - Schema v1: dbName="rag_vector_store", storeName="chunks"
 * - Warm start 시 인덱스 복원
 * - 결정성 유지: 같은 픽스처 입력이면 재시작 후에도 동일한 결과
 */
export class RealVectorStore implements VectorStore {
  private isInitialized = false;
  private chunks: Array<DocumentChunk & { embedding: EmbeddingVector }> = [];
  private indexVersion = "1.0.0";
  private db: IDBDatabase | null = null;

  async initialize(onProgress?: (progress: { progress: number; text: string }) => void): Promise<void> {
    if (this.isInitialized) return;

    if (!isIndexedDBAvailable()) {
      throw new Error("IndexedDB not available (non-web environment)");
    }

    if (onProgress) {
      onProgress({ progress: 0, text: "Opening IndexedDB..." });
    }

    try {
      this.db = await openDB();

      // Warm start: 복원 시도
      if (onProgress) {
        onProgress({ progress: 50, text: "Checking for existing index..." });
      }

      const restored = await this.restore();
      if (restored) {
        if (onProgress) {
          onProgress({ progress: 100, text: "Index restored from cache" });
        }
      } else {
        if (onProgress) {
          onProgress({ progress: 100, text: "Index ready (will build on first upsert)" });
        }
      }
    } catch (error: any) {
      console.warn("[RealVectorStore] IndexedDB initialization failed:", error);
      // IndexedDB 실패 시 인메모리로 폴백
      this.chunks = [];
    }

    this.isInitialized = true;
  }

  async upsert(chunks: DocumentChunk[]): Promise<void> {
    if (!this.isInitialized) {
      await this.initialize();
    }

    // 임베딩이 없는 청크는 에러 (임베딩은 외부에서 생성되어야 함)
    for (const chunk of chunks) {
      if (!chunk.embedding) {
        throw new Error(`Chunk ${chunk.id} missing embedding`);
      }

      const chunkWithEmbedding = { ...chunk, embedding: chunk.embedding };

      // 메모리 캐시 업데이트
      const existingIndex = this.chunks.findIndex((c) => c.id === chunk.id);
      if (existingIndex >= 0) {
        this.chunks[existingIndex] = chunkWithEmbedding;
      } else {
        this.chunks.push(chunkWithEmbedding);
      }

      // IndexedDB에 저장
      if (this.db) {
        await this.putToIndexedDB(chunkWithEmbedding);
      }
    }
  }

  private async putToIndexedDB(chunk: DocumentChunk & { embedding: EmbeddingVector }): Promise<void> {
    return new Promise((resolve, reject) => {
      if (!this.db) {
        reject(new Error("Database not initialized"));
        return;
      }

      const transaction = this.db.transaction(["chunks"], "readwrite");
      const store = transaction.objectStore("chunks");
      const request = store.put({
        id: chunk.id,
        text: chunk.text,
        embedding: chunk.embedding,
        metadata: chunk.metadata || {},
        indexVersion: this.indexVersion,
        updatedAt: Date.now(),
      });

      request.onsuccess = () => resolve();
      request.onerror = () => reject(request.error);
    });
  }

  async search(queryVector: EmbeddingVector, topK: number): Promise<SearchResult[]> {
    if (this.chunks.length === 0) return [];

    // 브루트포스 코사인 유사도 검색 (인메모리)
    const results: SearchResult[] = this.chunks.map((chunk) => ({
      chunk,
      score: cosineSimilarity(queryVector, chunk.embedding),
    }));

    // 점수 내림차순 정렬 및 topK 반환
    return results
      .sort((a, b) => b.score - a.score)
      .slice(0, topK)
      .filter((r) => r.score > 0);
  }

  async persist(): Promise<void> {
    // 이미 upsert에서 IndexedDB에 저장되므로, 여기서는 명시적 저장 완료만 표시
    if (this.db) {
      // 모든 청크가 이미 IndexedDB에 저장되어 있음
      console.log(`[RealVectorStore] persist() called: ${this.chunks.length} chunks already persisted`);
    }
  }

  async restore(): Promise<boolean> {
    if (!this.db) {
      return false;
    }

    try {
      const chunks = await this.getAllFromIndexedDB();
      if (chunks.length === 0) {
        return false; // 복원할 데이터 없음
      }

      // 메모리 캐시에 복원
      this.chunks = chunks;
      console.log(`[RealVectorStore] restore() completed: ${chunks.length} chunks restored`);
      return true;
    } catch (error: any) {
      console.warn("[RealVectorStore] restore() failed:", error);
      return false;
    }
  }

  private async getAllFromIndexedDB(): Promise<Array<DocumentChunk & { embedding: EmbeddingVector }>> {
    return new Promise((resolve, reject) => {
      if (!this.db) {
        reject(new Error("Database not initialized"));
        return;
      }

      const transaction = this.db.transaction(["chunks"], "readonly");
      const store = transaction.objectStore("chunks");
      const request = store.getAll();

      request.onsuccess = () => {
        const items = request.result as Array<{
          id: string;
          text: string;
          embedding: EmbeddingVector;
          metadata?: any;
        }>;

        const chunks: Array<DocumentChunk & { embedding: EmbeddingVector }> = items.map((item) => ({
          id: item.id,
          text: item.text,
          embedding: item.embedding,
          metadata: item.metadata,
        }));

        resolve(chunks);
      };

      request.onerror = () => reject(request.error);
    });
  }

  async clear(): Promise<void> {
    if (this.db) {
      const transaction = this.db.transaction(["chunks"], "readwrite");
      const store = transaction.objectStore("chunks");
      await new Promise<void>((resolve, reject) => {
        const request = store.clear();
        request.onsuccess = () => resolve();
        request.onerror = () => reject(request.error);
      });
    }

    this.chunks = [];
    this.isInitialized = false;
  }

  /**
   * 문서 개수 조회 (텔레메트리용)
   */
  getDocCount(): number {
    return this.chunks.length;
  }
}

/**
 * VectorStore 팩토리
 * 
 * ✅ R10-S5 P0-4: Live 모드에서 RealVectorStore 사용 (IndexedDB)
 * - Mock: StubVectorStore (인메모리, Network 0)
 * - Live: RealVectorStore (IndexedDB 영속화, 웹 환경에서만)
 */
export function getVectorStore(demoMode: "mock" | "live"): VectorStore {
  if (demoMode === "mock") {
    return new StubVectorStore();
  }

  // Live 모드: IndexedDB 사용 가능 여부 확인
  if (isIndexedDBAvailable()) {
    return new RealVectorStore();
  }

  // IndexedDB 사용 불가 시 Stub으로 폴백
  console.warn("[getVectorStore] IndexedDB not available, falling back to StubVectorStore");
  return new StubVectorStore();
}

