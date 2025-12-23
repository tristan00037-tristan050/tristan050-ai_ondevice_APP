/**
 * R10-S5: ContextBuilder 구현
 * 
 * 검색된 청크를 프롬프트 컨텍스트로 변환
 */

import type { ContextBuilder, SearchResult, RAGConfig } from "./types";

export class RAGContextBuilder implements ContextBuilder {
  constructor(private config: RAGConfig) {}

  buildContext(results: SearchResult[]): string {
    if (results.length === 0) return "";

    const contextParts: string[] = [];

    for (const result of results) {
      const chunk = result.chunk;
      const sourceInfo = chunk.metadata?.sourceTitle
        ? `[출처: ${chunk.metadata.sourceTitle}]`
        : chunk.metadata?.sourceId
        ? `[출처 ID: ${chunk.metadata.sourceId}]`
        : "";

      contextParts.push(`${sourceInfo}\n${chunk.text}`);
    }

    let context = contextParts.join("\n\n---\n\n");

    // 최대 문자 수 제한 (설정된 경우)
    if (this.config.maxContextChars && context.length > this.config.maxContextChars) {
      context = context.slice(0, this.config.maxContextChars) + "...";
    }

    return context;
  }
}

