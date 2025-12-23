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
 * Real Embedder (TODO: 실제 임베딩 모델 통합)
 * 
 * 예시 구조:
 * - WebGPU 기반 임베딩 모델 로딩
 * - BFF 프록시를 통한 모델 아티팩트 다운로드
 * - Progress 콜백 지원
 */
export class RealEmbedder implements Embedder {
  private isLoaded = false;

  async load(onProgress?: (progress: { progress: number; text: string }) => void): Promise<void> {
    if (this.isLoaded) return;

    // TODO: 실제 임베딩 모델 로딩
    // - 모델 아티팩트 경로: BFF 프록시 또는 동일 오리진
    // - WebGPU 우선, 폴백: wasm/CPU
    // - Progress 콜백으로 로딩 상태 전달

    if (onProgress) {
      onProgress({ progress: 0, text: "Loading embedding model..." });
      // 실제 로딩 로직
      onProgress({ progress: 100, text: "Embedding model ready" });
    }

    this.isLoaded = true;
  }

  async embed(text: string): Promise<EmbeddingVector> {
    if (!this.isLoaded) {
      await this.load();
    }

    // TODO: 실제 임베딩 모델로 변환
    throw new Error("RealEmbedder not implemented yet");
  }

  async embedBatch(texts: string[]): Promise<EmbeddingVector[]> {
    // TODO: 배치 임베딩 최적화
    return Promise.all(texts.map((text) => this.embed(text)));
  }
}

/**
 * Embedder 팩토리
 */
export function getEmbedder(demoMode: "mock" | "live"): Embedder {
  if (demoMode === "mock") {
    return new StubEmbedder();
  }

  // TODO: Live 모드에서 실제 임베딩 모델 사용 여부 결정
  // const useRealEmbedding = process.env.EXPO_PUBLIC_USE_REAL_EMBEDDING === "1";
  // return useRealEmbedding ? new RealEmbedder() : new StubEmbedder();

  return new StubEmbedder(); // 현재는 stub만
}

