/**
 * R10-S5: On-Device RAG (Retrieval-Augmented Generation) Types
 * 
 * 핵심 원칙:
 * - 데이터는 외부로 안 나감 (온디바이스 임베딩 + 온디바이스 검색)
 * - 게이트웨이 경계 준수 (초기 데이터 수집이 필요하면 BFF에서만 가져오고, 이후는 로컬 캐시/스토어)
 * - meta-only 텔레메트리 유지 (문서 원문/검색 결과 원문을 절대 텔레메트리로 보내지 않음)
 * - Mock/Live 쌍 유지 (mock=Network 0 강제)
 */

/**
 * 임베딩 벡터 타입
 */
export type EmbeddingVector = number[];

/**
 * 문서 청크 (검색 가능한 단위)
 */
export interface DocumentChunk {
  id: string;
  text: string; // 원문 (온디바이스에서만 사용, 텔레메트리 금지)
  metadata?: {
    sourceId?: string; // 출처 ID (예: ticket ID)
    sourceTitle?: string; // 출처 제목 (예: ticket subject)
    timestamp?: number;
    [key: string]: unknown;
  };
  embedding?: EmbeddingVector; // 임베딩 벡터 (선택적, lazy loading 가능)
}

/**
 * 검색 결과
 */
export interface SearchResult {
  chunk: DocumentChunk;
  score: number; // 유사도 점수 (0-1)
}

/**
 * Embedder 인터페이스
 * 텍스트를 벡터로 변환
 */
export interface Embedder {
  /**
   * 임베딩 모델 로딩
   */
  load(onProgress?: (progress: { progress: number; text: string }) => void): Promise<void>;

  /**
   * 텍스트를 임베딩 벡터로 변환
   */
  embed(text: string): Promise<EmbeddingVector>;

  /**
   * 여러 텍스트를 배치로 임베딩
   */
  embedBatch(texts: string[]): Promise<EmbeddingVector[]>;
}

/**
 * VectorStore 인터페이스
 * 벡터 저장 및 검색
 */
export interface VectorStore {
  /**
   * 인덱스 초기화/로딩
   */
  initialize(onProgress?: (progress: { progress: number; text: string }) => void): Promise<void>;

  /**
   * 문서 청크 추가/업데이트
   */
  upsert(chunks: DocumentChunk[]): Promise<void>;

  /**
   * 벡터 유사도 검색
   */
  search(queryVector: EmbeddingVector, topK: number): Promise<SearchResult[]>;

  /**
   * 인덱스 저장 (영속화)
   */
  persist(): Promise<void>;

  /**
   * 인덱스 복원 (Warm start)
   */
  restore(): Promise<boolean>; // true: 복원 성공, false: 복원 불가 (재빌드 필요)

  /**
   * 인덱스 초기화 (모든 데이터 삭제)
   */
  clear(): Promise<void>;
}

/**
 * Retriever 인터페이스
 * 쿼리에서 관련 문서 청크 검색
 */
export interface Retriever {
  /**
   * 쿼리로 관련 문서 검색
   */
  retrieve(query: string, topK: number): Promise<SearchResult[]>;
}

/**
 * ContextBuilder 인터페이스
 * 검색된 청크를 프롬프트 컨텍스트로 변환
 */
export interface ContextBuilder {
  /**
   * 검색 결과를 프롬프트 컨텍스트 문자열로 변환
   * (원문은 포함하되, 텔레메트리로는 보내지 않음)
   */
  buildContext(results: SearchResult[]): string;
}

/**
 * RAG 설정
 */
export interface RAGConfig {
  enabled: boolean;
  topK: number; // 검색할 상위 K개 문서
  minScore?: number; // 최소 유사도 점수 (이하 제외)
  maxContextChars?: number; // 최대 컨텍스트 문자 수
}

/**
 * RAG 메타데이터 (텔레메트리용, 원문 금지)
 */
export interface RAGMeta {
  ragEnabled: boolean;
  ragDocs: number; // 검색 대상 문서 수
  ragTopK: number;
  ragContextChars: number; // 주입한 컨텍스트 문자 수
  ragEmbeddingMs?: number;
  ragRetrieveMs?: number;
  ragIndexWarm?: boolean;
}

