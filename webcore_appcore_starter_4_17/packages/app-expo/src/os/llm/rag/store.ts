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

  getDocCount(): number {
    return this.chunks.length;
  }

  getMeta() {
    return {
      indexVersion: this.indexVersion,
      schemaVersion: 1,
      docCount: this.chunks.length,
      isInitialized: this.isInitialized,
    };
  }
}

/**
 * IndexedDB 헬퍼 (웹 환경 전용)
 * 
 * ✅ R10-S5 P1-3: DB_VERSION = 2 (v1→v2 마이그레이션 지원)
 */
const DB_NAME = "rag_vector_store";
const DB_VERSION = 2; // ✅ P1-3: v1 → v2 업그레이드

function isIndexedDBAvailable(): boolean {
  return typeof window !== "undefined" && "indexedDB" in window;
}

/**
 * IndexedDB 삭제 (실패 시 fallback용)
 */
function deleteDatabase(): Promise<void> {
  return new Promise((resolve, reject) => {
    if (!isIndexedDBAvailable()) {
      resolve();
      return;
    }

    const request = indexedDB.deleteDatabase(DB_NAME);
    request.onsuccess = () => {
      console.log("[RealVectorStore] Database deleted (fallback after migration failure)");
      resolve();
    };
    request.onerror = () => {
      console.warn("[RealVectorStore] Failed to delete database:", request.error);
      resolve(); // 실패해도 계속 진행 (재시도 가능)
    };
    request.onblocked = () => {
      console.warn("[RealVectorStore] Database deletion blocked (other connections open)");
      resolve(); // 블로킹되어도 계속 진행
    };
  });
}

function openDB(): Promise<IDBDatabase> {
  return new Promise((resolve, reject) => {
    if (!isIndexedDBAvailable()) {
      reject(new Error("IndexedDB not available"));
      return;
    }

    let upgradeFailed = false;

    const request = indexedDB.open(DB_NAME, DB_VERSION);

    // ✅ P1-3: v1→v2 마이그레이션 처리
    request.onupgradeneeded = (event) => {
      const db = (event.target as IDBOpenDBRequest).result;
      const oldVersion = event.oldVersion;
      const newVersion = event.newVersion;

      console.log(`[RealVectorStore] DB upgrade: v${oldVersion} → v${newVersion}`);

      try {
        // v1 → v2: Schema 변경 없음 (호환성 유지)
        // 기존 데이터는 그대로 유지됨 (IndexedDB 자동 처리)
        
        if (!db.objectStoreNames.contains("chunks")) {
          // v1에서 chunks가 없는 경우 (초기 생성)
          const store = db.createObjectStore("chunks", { keyPath: "id" });
          store.createIndex("sourceId", "metadata.sourceId", { unique: false });
        } else {
          // v1에서 v2로 업그레이드: 기존 스토어 유지, 인덱스 확인
          const store = request.transaction!.objectStore("chunks");
          if (!store.indexNames.contains("sourceId")) {
            store.createIndex("sourceId", "metadata.sourceId", { unique: false });
          }
        }

        console.log("[RealVectorStore] DB upgrade completed successfully");
      } catch (error: any) {
        console.error("[RealVectorStore] DB upgrade failed:", error);
        upgradeFailed = true;
        // Upgrade 실패 시 트랜잭션이 자동 롤백됨
        request.transaction!.abort();
      }
    };

    request.onsuccess = () => {
      if (upgradeFailed) {
        // Upgrade 실패 시 fallback: DB 삭제 후 재생성
        console.warn("[RealVectorStore] Upgrade failed, attempting fallback...");
        deleteDatabase()
          .then(() => {
            // 재시도 (이번에는 v2로 새로 생성)
            const retryRequest = indexedDB.open(DB_NAME, DB_VERSION);
            retryRequest.onsuccess = () => resolve(retryRequest.result);
            retryRequest.onerror = () => reject(retryRequest.error);
            retryRequest.onupgradeneeded = (e) => {
              const db = (e.target as IDBOpenDBRequest).result;
              if (!db.objectStoreNames.contains("chunks")) {
                const store = db.createObjectStore("chunks", { keyPath: "id" });
                store.createIndex("sourceId", "metadata.sourceId", { unique: false });
              }
            };
          })
          .catch((deleteError) => {
            console.error("[RealVectorStore] Failed to delete and retry:", deleteError);
            reject(new Error("Upgrade failed and fallback also failed"));
          });
      } else {
        resolve(request.result);
      }
    };

    request.onerror = () => {
      const error = request.error;
      console.error("[RealVectorStore] IndexedDB open failed:", error);
      
      // 일반 오류 시에도 fallback 시도
      deleteDatabase()
        .then(() => {
          const retryRequest = indexedDB.open(DB_NAME, DB_VERSION);
          retryRequest.onsuccess = () => resolve(retryRequest.result);
          retryRequest.onerror = () => reject(retryRequest.error || error);
          retryRequest.onupgradeneeded = (e) => {
            const db = (e.target as IDBOpenDBRequest).result;
            if (!db.objectStoreNames.contains("chunks")) {
              const store = db.createObjectStore("chunks", { keyPath: "id" });
              store.createIndex("sourceId", "metadata.sourceId", { unique: false });
            }
          };
        })
        .catch(() => {
          reject(error);
        });
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
  private indexVersion = "2.0.0"; // ✅ P1-3: v2로 업그레이드
  private db: IDBDatabase | null = null;
  private _indexBuildMs = 0;
  private _persistMs = 0;
  private _hydrateMs = 0;

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
      // ✅ P1-3: 실패 시 clear/rebuild 경로로 전환
      try {
        await this.clear();
        // DB 삭제 후 재시도
        await deleteDatabase();
        // 재초기화 시도 (이번에는 새로 생성)
        this.db = await openDB();
      } catch (fallbackError: any) {
        console.warn("[RealVectorStore] Fallback also failed:", fallbackError);
        // 최종 폴백: 인메모리로 전환
        this.chunks = [];
        this.db = null;
      }
    }

    this.isInitialized = true;
  }

  async upsert(chunks: DocumentChunk[]): Promise<void> {
    if (!this.isInitialized) {
      await this.initialize();
    }

    const startTime = Date.now();
    
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
    
    this._indexBuildMs = Date.now() - startTime;
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
    const startTime = Date.now();
    // 이미 upsert에서 IndexedDB에 저장되므로, 여기서는 명시적 저장 완료만 표시
    if (this.db) {
      // 모든 청크가 이미 IndexedDB에 저장되어 있음
      console.log(`[RealVectorStore] persist() called: ${this.chunks.length} chunks already persisted`);
    }
    this._persistMs = Date.now() - startTime;
  }

  async restore(): Promise<boolean> {
    if (!this.db) {
      return false;
    }

    const startTime = Date.now();
    try {
      const chunks = await this.getAllFromIndexedDB();
      if (chunks.length === 0) {
        return false; // 복원할 데이터 없음
      }

      // ✅ P1-3: v1 데이터 호환성 확인 (indexVersion 체크)
      // v1 데이터는 그대로 사용 가능 (schema 호환)
      const validChunks = chunks.filter((chunk: any) => {
        // v1 데이터는 indexVersion이 없을 수 있음 (호환)
        return chunk && chunk.id && chunk.text && chunk.embedding;
      });

      if (validChunks.length === 0) {
        console.warn("[RealVectorStore] No valid chunks found, clearing and rebuilding");
        await this.clear();
        return false;
      }

      // 메모리 캐시에 복원
      this.chunks = validChunks;
      this._hydrateMs = Date.now() - startTime;
      console.log(`[RealVectorStore] restore() completed: ${validChunks.length} chunks restored in ${this._hydrateMs}ms`);
      return true;
    } catch (error: any) {
      console.warn("[RealVectorStore] restore() failed:", error);
      // ✅ P1-3: 복원 실패 시 clear/rebuild 경로로 전환
      try {
        await this.clear();
      } catch (clearError: any) {
        console.warn("[RealVectorStore] clear() also failed:", clearError);
      }
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

  getMeta() {
    return {
      indexVersion: this.indexVersion,
      schemaVersion: 2, // ✅ P1-3: v2로 업그레이드
      docCount: this.chunks.length,
      isInitialized: this.isInitialized,
      indexBuildMs: this._indexBuildMs,
      persistMs: this._persistMs,
      hydrateMs: this._hydrateMs,
    };
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

