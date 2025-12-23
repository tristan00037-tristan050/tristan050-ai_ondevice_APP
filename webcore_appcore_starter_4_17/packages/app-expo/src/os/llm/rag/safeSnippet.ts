/**
 * R10-S5 P1-2: Safe Snippet 생성 함수
 * 
 * 원칙:
 * - 결정성: 동일 입력이면 항상 동일한 스니펫 반환
 * - 안전성: 제어문자/HTML/Markdown 해석 금지, plain text만
 * - 길이 제한: 상한 적용 (본문 과다 노출 금지)
 */

/**
 * Safe Snippet 생성
 * 
 * @param rawText 원본 텍스트
 * @param maxLength 최대 길이 (기본 160자)
 * @param queryTerms 선택적: 쿼리 키워드 (hit 기준 윈도우 추출용)
 * @returns 안전한 스니펫 (plain text, 길이 제한, 제어문자 제거)
 */
export function createSafeSnippet(
  rawText: string,
  maxLength: number = 160,
  queryTerms?: string[]
): string {
  if (!rawText || typeof rawText !== "string") {
    return "";
  }

  // 1. 제어문자 제거 + 공백 정규화
  let cleaned = rawText
    .replace(/[\x00-\x1F\x7F-\x9F]/g, "") // 제어문자 제거
    .replace(/[\r\n\t]+/g, " ") // 줄바꿈/탭 → 단일 공백
    .replace(/\s+/g, " ") // 연속 공백 → 단일 공백
    .trim();

  if (cleaned.length === 0) {
    return "";
  }

  // 2. 쿼리 키워드 기반 윈도우 추출 (결정적)
  if (queryTerms && queryTerms.length > 0) {
    const lowerText = cleaned.toLowerCase();
    let hitIndex = -1;
    
    // 첫 번째 키워드 hit 위치 찾기
    for (const term of queryTerms) {
      const termLower = term.toLowerCase();
      const idx = lowerText.indexOf(termLower);
      if (idx >= 0) {
        hitIndex = idx;
        break;
      }
    }

    if (hitIndex >= 0) {
      // 윈도우 추출: 앞 40~60자 + hit + 뒤 80~120자
      const beforeWindow = Math.max(0, hitIndex - 50);
      const afterWindow = Math.min(cleaned.length, hitIndex + 100);
      const windowText = cleaned.slice(beforeWindow, afterWindow);
      
      // 윈도우가 maxLength보다 짧으면 윈도우 사용, 아니면 전체에서 자르기
      if (windowText.length <= maxLength) {
        cleaned = windowText;
      }
    }
  }

  // 3. 길이 상한 적용
  if (cleaned.length > maxLength) {
    // 단어 경계에서 자르기 (마지막 공백 위치 찾기)
    const truncated = cleaned.slice(0, maxLength);
    const lastSpace = truncated.lastIndexOf(" ");
    if (lastSpace > maxLength * 0.7) {
      // 마지막 공백이 70% 이상 위치에 있으면 그곳에서 자르기
      cleaned = truncated.slice(0, lastSpace) + "...";
    } else {
      // 그렇지 않으면 maxLength에서 자르기
      cleaned = truncated + "...";
    }
  }

  return cleaned;
}

/**
 * Safe Snippet 검증 (테스트/게이트용)
 * 
 * @param snippet 스니펫 텍스트
 * @returns 검증 결과
 */
export function validateSafeSnippet(snippet: string): {
  isValid: boolean;
  issues: string[];
} {
  const issues: string[] = [];

  // 제어문자 검사
  if (/[\x00-\x1F\x7F-\x9F]/.test(snippet)) {
    issues.push("제어문자 포함");
  }

  // HTML 태그 검사
  if (/<[^>]+>/.test(snippet)) {
    issues.push("HTML 태그 포함");
  }

  // 길이 검사 (상한 200자, 권장 160자)
  if (snippet.length > 200) {
    issues.push(`길이 초과 (${snippet.length}자 > 200자)`);
  }

  return {
    isValid: issues.length === 0,
    issues,
  };
}

