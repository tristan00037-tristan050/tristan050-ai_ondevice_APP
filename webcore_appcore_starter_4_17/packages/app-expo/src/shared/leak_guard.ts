/**
 * Leakage Firewall v1 + v2
 * v1: 입력(로컬 원문)과 출력(버틀러 결과) 사이 중복률/연속 문자열 길이 검사
 * v2: 인코딩/암호문 의심 패턴 통계적 차단 (압축률/엔트로피/Base64 의심)
 * 임계치 초과 시 출력 표시 차단 + Export 차단 (Fail-Closed)
 */

export interface LeakGuardResult {
  pass: boolean;
  blocked: boolean;
  reason_code?: string;
  dup_ratio?: number;
  max_contiguous_length?: number;
  dup_ratio_bucket?: string;
  // v2 지표 (meta-only)
  compression_ratio_bucket?: string;
  char_entropy_bucket?: string;
  base64_suspect?: boolean;
  next_steps?: string[];
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
 * Leakage Firewall v2: 압축률 계산 (zlib)
 * React Native 환경에서는 TextEncoder/TextDecoder를 사용하여 바이트 길이 추정
 */
function calculateCompressionRatio(text: string): number {
  if (!text || text.length === 0) {
    return 1.0;
  }

  try {
    // 브라우저/React Native 환경: UTF-8 바이트 길이 추정
    const originalBytes = new TextEncoder().encode(text).length;
    
    // 간단한 압축률 추정 (실제 zlib 대신 휴리스틱)
    // 고엔트로피 텍스트는 압축률이 낮고, 반복이 많으면 압축률이 높음
    // 실제 zlib은 Node.js 환경에서만 사용 가능하므로, 여기서는 추정값 사용
    let compressedEstimate = originalBytes;
    
    // 반복 패턴 감지 (간단한 RLE 추정)
    let runLength = 1;
    let maxRun = 1;
    for (let i = 1; i < text.length; i++) {
      if (text[i] === text[i - 1]) {
        runLength++;
        maxRun = Math.max(maxRun, runLength);
      } else {
        runLength = 1;
      }
    }
    
    // 반복이 많으면 압축률이 높음 (추정)
    if (maxRun > 3) {
      compressedEstimate = Math.floor(originalBytes * 0.7); // 30% 압축 추정
    }
    
    return originalBytes > 0 ? compressedEstimate / originalBytes : 1.0;
  } catch {
    return 1.0;
  }
}

/**
 * Leakage Firewall v2: 문자 엔트로피 계산
 */
function calculateCharEntropy(text: string): number {
  if (!text || text.length === 0) {
    return 0;
  }

  // 문자 빈도 계산
  const charCounts: Record<string, number> = {};
  for (const char of text) {
    charCounts[char] = (charCounts[char] || 0) + 1;
  }

  const length = text.length;
  const uniqueChars = Object.keys(charCounts).length;
  
  if (uniqueChars <= 1) {
    return 0;
  }

  // Shannon 엔트로피 계산
  let entropy = 0;
  for (const count of Object.values(charCounts)) {
    const probability = count / length;
    if (probability > 0) {
      entropy -= probability * Math.log2(probability);
    }
  }

  // 정규화 (최대 엔트로피는 log2(uniqueChars))
  const maxEntropy = Math.log2(uniqueChars);
  return maxEntropy > 0 ? entropy / maxEntropy : 0;
}

/**
 * Leakage Firewall v2: Base64 의심 패턴 감지
 */
function detectBase64Suspect(text: string): boolean {
  if (!text || text.length < 4) {
    return false;
  }

  // Base64 패턴: A-Z, a-z, 0-9, +, /, = (패딩)
  const base64Pattern = /^[A-Za-z0-9+/]+=*$/;
  
  // 길이가 4의 배수이고 Base64 문자만 포함
  const trimmed = text.trim();
  if (trimmed.length >= 8 && trimmed.length % 4 === 0) {
    if (base64Pattern.test(trimmed)) {
      // = 패딩이 끝에만 있는지 확인
      const paddingIndex = trimmed.indexOf('=');
      if (paddingIndex === -1 || paddingIndex === trimmed.length - 1 || paddingIndex === trimmed.length - 2) {
        // 엔트로피가 높으면 Base64 의심 (암호문 가능성)
        const entropy = calculateCharEntropy(trimmed);
        if (entropy > 0.8) {
          return true;
        }
      }
    }
  }

  return false;
}

/**
 * 압축률 버킷 분류 (meta-only)
 */
function getCompressionRatioBucket(ratio: number): string {
  if (ratio >= 0.9) return 'VERY_HIGH'; // 압축 거의 안 됨 (고엔트로피)
  if (ratio >= 0.7) return 'HIGH';
  if (ratio >= 0.5) return 'MEDIUM';
  if (ratio >= 0.3) return 'LOW';
  return 'VERY_LOW'; // 압축 잘 됨 (반복 많음)
}

/**
 * 문자 엔트로피 버킷 분류 (meta-only)
 */
function getCharEntropyBucket(entropy: number): string {
  if (entropy >= 0.9) return 'VERY_HIGH'; // 고엔트로피 (암호문/인코딩 의심)
  if (entropy >= 0.7) return 'HIGH';
  if (entropy >= 0.5) return 'MEDIUM';
  if (entropy >= 0.3) return 'LOW';
  return 'VERY_LOW'; // 저엔트로피 (반복 많음)
}

/**
 * Leakage Firewall v2 검사
 */
function checkLeakageV2(output: string): {
  blocked: boolean;
  reason_code?: string;
  compression_ratio_bucket?: string;
  char_entropy_bucket?: string;
  base64_suspect?: boolean;
  next_steps?: string[];
} {
  if (!output || output.length === 0) {
    return { blocked: false };
  }

  // v2 지표 계산 (meta-only)
  const compressionRatio = calculateCompressionRatio(output);
  const compressionRatioBucket = getCompressionRatioBucket(compressionRatio);
  
  const charEntropy = calculateCharEntropy(output);
  const charEntropyBucket = getCharEntropyBucket(charEntropy);
  
  const base64Suspect = detectBase64Suspect(output);

  // 이상치 판정 (임계치)
  const ANOMALY_COMPRESSION_RATIO_THRESHOLD = 0.9; // 압축률 90% 이상 (고엔트로피)
  const ANOMALY_ENTROPY_THRESHOLD = 0.85; // 엔트로피 85% 이상 (암호문 의심)
  
  let blocked = false;
  let reasonCode: string | undefined;
  const nextSteps: string[] = [];

  // Base64 의심 차단
  if (base64Suspect) {
    blocked = true;
    reasonCode = 'BASE64_SUSPECT';
    nextSteps.push('출력에 Base64 인코딩 패턴이 감지되었습니다');
    nextSteps.push('원문이 인코딩되어 전달되지 않았는지 확인하세요');
  }
  
  // 고엔트로피 + 압축률 높음 (암호문 의심)
  if (!blocked && charEntropy >= ANOMALY_ENTROPY_THRESHOLD && compressionRatio >= ANOMALY_COMPRESSION_RATIO_THRESHOLD) {
    blocked = true;
    reasonCode = 'HIGH_ENTROPY_COMPRESSION_ANOMALY';
    nextSteps.push('출력의 엔트로피와 압축률이 이상치 범위입니다');
    nextSteps.push('암호문 또는 인코딩된 텍스트가 포함되었을 수 있습니다');
  }

  return {
    blocked,
    reason_code: reasonCode,
    compression_ratio_bucket: compressionRatioBucket,
    char_entropy_bucket: charEntropyBucket,
    base64_suspect: base64Suspect,
    next_steps: nextSteps.length > 0 ? nextSteps : undefined,
  };
}

/**
 * Leakage Firewall 검사 (v1 + v2 통합)
 */
export function checkLeakage(input: string, output: string): LeakGuardResult {
  // 입력/출력이 없으면 PASS
  if (!input || !output) {
    return {
      pass: true,
      blocked: false,
    };
  }

  // v1 검사 (중복률/연속 문자열)
  const dupRatio = calculateDupRatio(input, output);
  const dupRatioBucket = getDupRatioBucket(dupRatio);
  const maxContiguousLength = findMaxContiguousLength(input, output);

  // v1 임계치 검사
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

  // v2 검사 (인코딩/암호문 의심)
  const v2Result = checkLeakageV2(output);
  if (v2Result.blocked) {
    return {
      pass: false,
      blocked: true,
      reason_code: v2Result.reason_code,
      dup_ratio: dupRatio,
      max_contiguous_length: maxContiguousLength,
      dup_ratio_bucket: dupRatioBucket,
      compression_ratio_bucket: v2Result.compression_ratio_bucket,
      char_entropy_bucket: v2Result.char_entropy_bucket,
      base64_suspect: v2Result.base64_suspect,
      next_steps: v2Result.next_steps,
    };
  }

  // PASS (v1 + v2 모두 통과)
  return {
    pass: true,
    blocked: false,
    dup_ratio: dupRatio,
    max_contiguous_length: maxContiguousLength,
    dup_ratio_bucket: dupRatioBucket,
    compression_ratio_bucket: v2Result.compression_ratio_bucket,
    char_entropy_bucket: v2Result.char_entropy_bucket,
    base64_suspect: v2Result.base64_suspect,
  };
}

/**
 * 감사 로그용 meta-only 정보 추출 (v1 + v2)
 */
export function extractLeakageAudit(result: LeakGuardResult): Record<string, unknown> {
  const audit: Record<string, unknown> = {
    blocked: result.blocked ?? false,
    reason_code: result.reason_code,
    dup_ratio_bucket: result.dup_ratio_bucket,
    blocked_count: result.blocked ? 1 : 0,
  };

  // v2 지표 추가 (meta-only, 원문 없음)
  if (result.compression_ratio_bucket !== undefined) {
    audit.compression_ratio_bucket = result.compression_ratio_bucket;
  }
  if (result.char_entropy_bucket !== undefined) {
    audit.char_entropy_bucket = result.char_entropy_bucket;
  }
  if (result.base64_suspect !== undefined) {
    audit.base64_suspect = result.base64_suspect;
  }

  return audit;
}

