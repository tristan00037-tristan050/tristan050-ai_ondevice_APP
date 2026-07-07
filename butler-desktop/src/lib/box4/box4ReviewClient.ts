import { sidecarFetch, uiSafeSidecarErrorMessage } from '../sidecarFetch';
import { parseAnalyzeStreamResult } from '../cards/analyzeStreamResult';
import { prepareCardTextFiles, type PreparedCardFile } from '../cards/fileText';

export type Box4IssueType = 'MISSING' | 'ERROR' | 'INCONSISTENCY' | 'STYLE' | 'SUGGESTION';
export type Box4Confidence = 'HIGH' | 'MEDIUM' | 'LOW';

export type Box4Issue = {
  location: string;
  issue_type: Box4IssueType;
  original_text: string;
  suggestion: string;
  confidence: Box4Confidence;
};

export type Box4DocumentReviewResult = {
  schema_version: 'card_04.document_review.v1';
  issues: Box4Issue[];
  overall_score: number;
  summary: string;
  review_required: boolean;
  warnings: string[];
  raw_log_zero?: boolean;
  external_send_zero?: boolean;
};

export type Box4DocumentReviewRequest = {
  targetDocument: string;
  referenceFiles: File[];
  signal?: AbortSignal;
};

export type Box4DocumentReviewResponse = {
  result: Box4DocumentReviewResult;
  preparedFiles: PreparedCardFile[];
};

const ISSUE_TYPES = new Set<Box4IssueType>(['MISSING', 'ERROR', 'INCONSISTENCY', 'STYLE', 'SUGGESTION']);
const CONFIDENCES = new Set<Box4Confidence>(['HIGH', 'MEDIUM', 'LOW']);
const REDACTED_SECRET_PLACEHOLDER = '[민감정보 원문 생략]';
const SECRET_TEXT_RE =
  /(?:sk-[A-Za-z0-9._-]{10,}|AKIA[0-9A-Z]{16}|-----BEGIN\s+[A-Z ]*PRIVATE KEY-----|(?:password|token|api\s*key|비밀번호|비번|암호|패스워드)\s*[:=：]\s*[^\s,;]{4,})/i;
const ISSUE_KEYS = new Set(['location', 'issue_type', 'original_text', 'suggestion', 'confidence']);
const REQUIRED_RESULT_KEYS = new Set(['schema_version', 'issues', 'overall_score', 'summary', 'review_required', 'warnings']);
const OPTIONAL_RESULT_KEYS = new Set(['raw_log_zero', 'external_send_zero']);

function hasOnlyAllowedKeys(
  record: Record<string, unknown>,
  required: ReadonlySet<string>,
  optional: ReadonlySet<string> = new Set()
): boolean {
  for (const key of required) {
    if (!(key in record)) return false;
  }
  return Object.keys(record).every(key => required.has(key) || optional.has(key));
}

function stringArray(value: unknown): string[] | null {
  if (!Array.isArray(value)) return null;
  if (!value.every(item => typeof item === 'string')) return null;
  return value;
}

function validateIssue(value: unknown): Box4Issue | null {
  if (!value || typeof value !== 'object') return null;
  const record = value as Record<string, unknown>;
  if (!hasOnlyAllowedKeys(record, ISSUE_KEYS)) return null;
  const issueType = record.issue_type;
  const confidence = record.confidence;
  if (
    typeof record.location !== 'string' ||
    typeof issueType !== 'string' ||
    !ISSUE_TYPES.has(issueType as Box4IssueType) ||
    typeof record.original_text !== 'string' ||
    record.original_text.length > 300 ||
    typeof record.suggestion !== 'string' ||
    typeof confidence !== 'string' ||
    !CONFIDENCES.has(confidence as Box4Confidence)
  ) {
    return null;
  }
  return {
    location: record.location,
    issue_type: issueType as Box4IssueType,
    original_text: record.original_text,
    suggestion: record.suggestion,
    confidence: confidence as Box4Confidence,
  };
}

export function validateBox4DocumentReviewResult(value: unknown): Box4DocumentReviewResult | null {
  if (!value || typeof value !== 'object') return null;
  const record = value as Record<string, unknown>;
  if (
    !hasOnlyAllowedKeys(record, REQUIRED_RESULT_KEYS, OPTIONAL_RESULT_KEYS) ||
    record.schema_version !== 'card_04.document_review.v1' ||
    !Array.isArray(record.issues) ||
    typeof record.overall_score !== 'number' ||
    !Number.isInteger(record.overall_score) ||
    record.overall_score < 0 ||
    record.overall_score > 100 ||
    typeof record.summary !== 'string' ||
    typeof record.review_required !== 'boolean' ||
    (record.raw_log_zero !== undefined && typeof record.raw_log_zero !== 'boolean') ||
    (record.external_send_zero !== undefined && typeof record.external_send_zero !== 'boolean')
  ) {
    return null;
  }
  const issues = record.issues.map(validateIssue);
  if (issues.some(item => item === null)) return null;
  const warnings = stringArray(record.warnings);
  if (!warnings) return null;
  return {
    schema_version: 'card_04.document_review.v1',
    issues: issues as Box4Issue[],
    overall_score: record.overall_score,
    summary: record.summary,
    review_required: record.review_required,
    warnings,
    raw_log_zero: record.raw_log_zero === true,
    external_send_zero: record.external_send_zero === true,
  };
}

function hasUnredactedSecretText(value: string): boolean {
  return value !== REDACTED_SECRET_PLACEHOLDER && SECRET_TEXT_RE.test(value);
}

function renderedStrings(value: unknown): string[] {
  if (typeof value === 'string') return [value];
  if (Array.isArray(value)) return value.flatMap(renderedStrings);
  if (value && typeof value === 'object') {
    return Object.values(value as Record<string, unknown>).flatMap(renderedStrings);
  }
  return [];
}

export function hasBox4SecretLeak(result: Box4DocumentReviewResult): boolean {
  return renderedStrings(result).some(hasUnredactedSecretText);
}

export async function createBox4DocumentReview(request: Box4DocumentReviewRequest): Promise<Box4DocumentReviewResponse> {
  const targetDocument = request.targetDocument.trim();
  if (!targetDocument) {
    throw new Error('검토 대상 문서를 입력해 주세요.');
  }

  const prepared = await prepareCardTextFiles(request.referenceFiles);
  const formData = new FormData();
  formData.append('query', targetDocument);
  formData.append('card_mode', '4');
  formData.append('total_chunks', '1');
  prepared.files.forEach((item, index) => formData.append(`file_${index}`, item.file));
  formData.append('file_count', String(prepared.files.length));

  try {
    const response = await sidecarFetch('/api/analyze/stream', {
      method: 'POST',
      body: formData,
      signal: request.signal,
    });
    if (!response.ok) {
      throw new Error('BOX4_ANALYZE_STREAM_FAILED');
    }
    const body = await response.text();
    const result = parseAnalyzeStreamResult(body, validateBox4DocumentReviewResult);
    if (hasBox4SecretLeak(result)) {
      throw new Error('민감정보가 포함되어 결과를 표시하지 않았습니다.');
    }
    return { result, preparedFiles: prepared.files };
  } catch (error) {
    if (error instanceof Error && error.name === 'AbortError') throw error;
    const message = uiSafeSidecarErrorMessage(error);
    if (message !== '요청 처리 중 오류가 발생했습니다. 잠시 후 다시 시도해 주세요.') {
      throw new Error(message);
    }
    throw error;
  }
}
