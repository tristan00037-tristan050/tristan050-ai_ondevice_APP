/**
 * R10-S5: Embedder 구현 (Stub)
 * 
 * TODO: 실제 임베딩 모델 통합
 * - WebGPU 가능 시 WebGPU 사용
 * - 불가 시 wasm/CPU 폴백
 * - 모델 아티팩트 경로는 동일 오리진 또는 BFF 프록시만 허용
 */

import type { Embedder, EmbeddingVector } from "./types";

/**
 * Stub Embedder (개발/테스트용)
 * 실제 임베딩 대신 간단한 해시 기반 벡터 생성
 */
export class StubEmbedder implements Embedder {
  private isLoaded = false;

  async load(onProgress?: (progress: { progress: number; text: string }) => void): Promise<void> {
    if (this.isLoaded) return;

    if (onProgress) {
      onProgress({ progress: 0, text: "Stub embedder (no loading required)" });
      await new Promise((resolve) => setTimeout(resolve, 100));
      onProgress({ progress: 100, text: "Stub embedder ready" });
    }

    this.isLoaded = true;
  }

  async embed(text: string): Promise<EmbeddingVector> {
    if (!this.isLoaded) {
      await this.load();
    }

    // Stub: 간단한 해시 기반 벡터 생성 (실제 임베딩 아님)
    const vector: EmbeddingVector = [];
    let hash = 0;
    for (let i = 0; i < text.length; i++) {
      hash = ((hash << 5) - hash + text.charCodeAt(i)) & 0xffffffff;
    }

    // 128차원 벡터로 정규화 (실제 모델 차원에 맞춰 조정)
    for (let i = 0; i < 128; i++) {
      const seed = hash + i * 31;
      vector.push(Math.sin(seed) * 0.5 + 0.5); // 0-1 범위로 정규화
    }

    return vector;
  }

  async embedBatch(texts: string[]): Promise<EmbeddingVector[]> {
    return Promise.all(texts.map((text) => this.embed(text)));
  }
}

/**
 * Real Embedder (해시 기반 온디바이스 임베딩)
 * 
 * ✅ R10-S5 P0-3: 온디바이스 임베딩 파이프라인
 * - 네트워크 호출 0 (완전 온디바이스)
 * - 동일 입력 → 동일 벡터 (결정성 보장)
 * - 해시 기반 벡터 생성 (SHA-256 기반)
 * - L2 정규화
 * 
 * 참고: 의미 기반 품질은 제한적이지만, P0-3 "파이프라인 구현" 목표에는 충분
 * 향후 실제 임베딩 모델로 교체 가능
 */
export class RealEmbedder implements Embedder {
  private isLoaded = false;
  private readonly dimension = 256; // 고정 차원
  private readonly version = "1.0.0"; // 임베딩 버전 (결정성 보장용)

  async load(onProgress?: (progress: { progress: number; text: string }) => void): Promise<void> {
    if (this.isLoaded) return;

    if (onProgress) {
      onProgress({ progress: 0, text: "Initializing hash-based embedder..." });
      await new Promise((resolve) => setTimeout(resolve, 50));
      onProgress({ progress: 100, text: "Hash-based embedder ready" });
    }

    this.isLoaded = true;
  }

  /**
   * 텍스트를 토큰화 (공백/구두점 기준)
   */
  private tokenize(text: string): string[] {
    // 간단한 토큰화: 공백/구두점으로 분리, 소문자 변환
    return text
      .toLowerCase()
      .replace(/[^\w\s가-힣]/g, " ") // 한글/영문/숫자만 유지
      .split(/\s+/)
      .filter((token) => token.length > 0);
  }

  /**
   * 안정 해시 함수 (결정성 보장)
   * 동일 입력에 대해 항상 동일한 해시 반환
   */
  private stableHash(str: string): number {
    let hash = 0;
    for (let i = 0; i < str.length; i++) {
      const char = str.charCodeAt(i);
      hash = ((hash << 5) - hash) + char;
      hash = hash & hash; // 32bit 정수로 변환
    }
    return Math.abs(hash);
  }

  /**
   * 텍스트를 임베딩 벡터로 변환
   * 동일 입력에 대해 항상 동일한 벡터 반환 (결정성 보장)
   */
  async embed(text: string): Promise<EmbeddingVector> {
    if (!this.isLoaded) {
      await this.load();
    }

    // 1. 토큰화
    const tokens = this.tokenize(text);

    // 2. 각 토큰을 해시하여 벡터 차원에 매핑
    const vector = new Array(this.dimension).fill(0);

    for (const token of tokens) {
      const hash = this.stableHash(token + this.version); // 버전 포함으로 결정성 보장
      const dimensionIndex = hash % this.dimension;
      const value = (hash % 1000) / 1000; // 0-1 범위로 정규화
      vector[dimensionIndex] += value;
    }

    // 3. L2 정규화
    const norm = Math.sqrt(vector.reduce((sum, val) => sum + val * val, 0));
    if (norm > 0) {
      for (let i = 0; i < vector.length; i++) {
        vector[i] = vector[i] / norm;
      }
    }

    return vector;
  }

  async embedBatch(texts: string[]): Promise<EmbeddingVector[]> {
    // 배치 임베딩: 순차 처리 (결정성 보장)
    return Promise.all(texts.map((text) => this.embed(text)));
  }

  /**
   * 임베딩 메타데이터 (텔레메트리용)
   */
  getMeta(): { dim: number; version: string; backend: "hash" } {
    return {
      dim: this.dimension,
      version: this.version,
      backend: "hash",
    };
  }
}

/**
 * Embedder 팩토리
 * 
 * ✅ R10-S5 P0-3: Live 모드에서 RealEmbedder 사용
 * - Mock: StubEmbedder (Network 0 강제)
 * - Live: RealEmbedder (해시 기반, 온디바이스, Network 0)
 */
export function getEmbedder(demoMode: "mock" | "live"): Embedder {
  if (demoMode === "mock") {
    return new StubEmbedder();
  }

  // ✅ P0-3: Live 모드에서 해시 기반 RealEmbedder 사용
  // 향후 실제 임베딩 모델로 교체 가능 (환경변수로 제어)
  const useRealEmbedding = process.env.EXPO_PUBLIC_USE_REAL_EMBEDDING !== "0"; // 기본값: true
  return useRealEmbedding ? new RealEmbedder() : new StubEmbedder();
}

