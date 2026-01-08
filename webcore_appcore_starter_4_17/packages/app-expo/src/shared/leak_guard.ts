/**
 * Leakage Firewall v1
 * 입력(로컬 원문)과 출력(버틀러 결과) 사이 중복률/연속 문자열 길이 검사
 * 임계치 초과 시 출력 표시 차단 + Export 차단 (Fail-Closed)
 */

export interface LeakGuardResult {
  pass: boolean;
  blocked: boolean;
  reason_code?: string;
  dup_ratio?: number;
  max_contiguous_length?: number;
  dup_ratio_bucket?: string;
}

// 임계치 설정
const MAX_DUP_RATIO = 0.3; // 중복률 30% 초과 시 차단
const MAX_CONTIGUOUS_LENGTH = 20; // 연속 문자열 20자 초과 시 차단

/**
 * 중복률 계산 (입력과 출력 사이)
 */
function calculateDupRatio(input: string, output: string): number {
  if (!input || !output || input.length === 0 || output.length === 0) {
    return 0;
  }

  // 입력을 토큰으로 분리 (공백 기준)
  const inputTokens = input.toLowerCase().split(/\s+/).filter(t => t.length > 0);
  const outputTokens = output.toLowerCase().split(/\s+/).filter(t => t.length > 0);

  if (inputTokens.length === 0 || outputTokens.length === 0) {
    return 0;
  }

  // 중복 토큰 개수 계산
  const inputTokenSet = new Set(inputTokens);
  const duplicateCount = outputTokens.filter(t => inputTokenSet.has(t)).length;

  return duplicateCount / outputTokens.length;
}

/**
 * 최대 연속 문자열 길이 계산
 */
function findMaxContiguousLength(input: string, output: string): number {
  if (!input || !output || input.length === 0 || output.length === 0) {
    return 0;
  }

  const inputLower = input.toLowerCase();
  const outputLower = output.toLowerCase();

  let maxLength = 0;

  // 슬라이딩 윈도우로 연속 문자열 찾기
  for (let i = 0; i <= outputLower.length - 3; i++) {
    for (let len = 3; len <= Math.min(outputLower.length - i, inputLower.length); len++) {
      const substring = outputLower.substring(i, i + len);
      if (inputLower.includes(substring)) {
        maxLength = Math.max(maxLength, len);
      }
    }
  }

  return maxLength;
}

/**
 * 중복률 버킷 분류 (meta-only)
 */
function getDupRatioBucket(ratio: number): string {
  if (ratio === 0) return 'ZERO';
  if (ratio < 0.1) return 'LOW';
  if (ratio < 0.3) return 'MEDIUM';
  return 'HIGH';
}

/**
 * Leakage Firewall 검사
 */
export function checkLeakage(input: string, output: string): LeakGuardResult {
  // 입력/출력이 없으면 PASS
  if (!input || !output) {
    return {
      pass: true,
      blocked: false,
    };
  }

  // 중복률 계산
  const dupRatio = calculateDupRatio(input, output);
  const dupRatioBucket = getDupRatioBucket(dupRatio);

  // 최대 연속 문자열 길이 계산
  const maxContiguousLength = findMaxContiguousLength(input, output);

  // 임계치 검사
  if (dupRatio > MAX_DUP_RATIO) {
    return {
      pass: false,
      blocked: true,
      reason_code: 'DUP_RATIO_EXCEEDED',
      dup_ratio: dupRatio,
      max_contiguous_length: maxContiguousLength,
      dup_ratio_bucket: dupRatioBucket,
    };
  }

  if (maxContiguousLength > MAX_CONTIGUOUS_LENGTH) {
    return {
      pass: false,
      blocked: true,
      reason_code: 'CONTIGUOUS_LENGTH_EXCEEDED',
      dup_ratio: dupRatio,
      max_contiguous_length: maxContiguousLength,
      dup_ratio_bucket: dupRatioBucket,
    };
  }

  return {
    pass: true,
    blocked: false,
    dup_ratio: dupRatio,
    max_contiguous_length: maxContiguousLength,
    dup_ratio_bucket: dupRatioBucket,
  };
}

/**
 * 여러 출력 항목에 대한 일괄 검사
 */
export function checkLeakageBatch(
  input: string,
  outputs: Array<{ title?: string; description?: string; rationale?: string }>
): LeakGuardResult {
  for (const output of outputs) {
    const outputText = [output.title, output.description, output.rationale]
      .filter(Boolean)
      .join(' ');

    if (!outputText) {
      continue;
    }

    const result = checkLeakage(input, outputText);
    if (!result.pass) {
      return result;
    }
  }

  return {
    pass: true,
    blocked: false,
  };
}

/**
 * 감사 로그용 meta-only 정보 추출
 */
export function extractLeakageAudit(result: LeakGuardResult): Record<string, unknown> {
  return {
    blocked: result.blocked ?? false,
    reason_code: result.reason_code,
    dup_ratio_bucket: result.dup_ratio_bucket,
    blocked_count: result.blocked ? 1 : 0,
  };
}

