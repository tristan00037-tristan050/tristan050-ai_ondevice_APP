import { sidecarFetch, uiSafeSidecarErrorMessage } from '../sidecarFetch';
import { parseAnalyzeStreamResult } from '../cards/analyzeStreamResult';
import { prepareCardTextFiles, type PreparedCardFile } from '../cards/fileText';

export type Box6Confidence = 'HIGH' | 'MEDIUM' | 'LOW' | 'UNFILLED';

export type Box6FieldMapping = {
  target_label: string;
  output_value: string;
  confidence: Box6Confidence;
  source_ref: string;
  reason_code: string;
};

export type Box6FormFillResult = {
  schema_version: 'card_06.form_fill.v1';
  filled_form: string;
  field_mappings: Box6FieldMapping[];
  unfilled_fields: string[];
  review_required: string[];
  warnings: string[];
};

export type Box6FormFillRequest = {
  blankForm: string;
  files: File[];
  signal?: AbortSignal;
};

export type Box6FormFillResponse = {
  result: Box6FormFillResult;
  preparedFiles: PreparedCardFile[];
};

const CONFIDENCES = new Set<Box6Confidence>(['HIGH', 'MEDIUM', 'LOW', 'UNFILLED']);
const SECRET_LABEL_RE =
  /\b(?:api\s*key|token|secret|password|passwd|credential|access\s*key|private\s*key|client\s*secret|auth(?:entication)?\s*key)\b|(?:비밀번호|비번|암호|패스워드|토큰|인증\s*키|보안\s*키|개인\s*키|시크릿|API\s*키|에이피아이\s*키)/i;
const SECRET_VALUE_RE =
  /(?:sk-[A-Za-z0-9._-]{10,}|AKIA[0-9A-Z]{16}|-----BEGIN\s+[A-Z ]*PRIVATE KEY-----|(?:password|token|api\s*key|비밀번호|비번|암호)\s*[:=：]\s*[^\s,;]{4,})/i;
const UNFILLED_VALUES = new Set(['', 'UNFILLED', '[미기입]', '[확인 필요]', '검토 필요', '미기입', '[민감정보 원문 생략]']);
const LEGACY_SOURCE_KEY = ['source', 'excerpt'].join('_');
const SECRET_GUARD_ERROR = 'BOX6_SECRET_GUARD_BLOCKED';
const RESULT_KEYS = new Set(['schema_version', 'filled_form', 'field_mappings', 'unfilled_fields', 'review_required', 'warnings']);
const MAPPING_KEYS = new Set(['target_label', 'output_value', 'confidence', 'source_ref', 'reason_code']);

function hasExactKeys(record: Record<string, unknown>, expected: ReadonlySet<string>): boolean {
  if (Object.keys(record).length !== expected.size) return false;
  return Object.keys(record).every(key => expected.has(key));
}

function stringArray(value: unknown): string[] | null {
  if (!Array.isArray(value)) return null;
  if (!value.every(item => typeof item === 'string')) return null;
  return value;
}

function validateMapping(value: unknown): Box6FieldMapping | null {
  if (!value || typeof value !== 'object') return null;
  const record = value as Record<string, unknown>;
  if (LEGACY_SOURCE_KEY in record || 'review_required' in record) {
    throw new Error('BOX6_LEGACY_MAPPING_SCHEMA');
  }
  if (!hasExactKeys(record, MAPPING_KEYS)) {
    return null;
  }
  const confidence = record.confidence;
  if (
    typeof record.target_label !== 'string' ||
    typeof record.output_value !== 'string' ||
    typeof confidence !== 'string' ||
    !CONFIDENCES.has(confidence as Box6Confidence) ||
    typeof record.source_ref !== 'string' ||
    typeof record.reason_code !== 'string'
  ) {
    return null;
  }
  return {
    target_label: record.target_label,
    output_value: record.output_value,
    confidence: confidence as Box6Confidence,
    source_ref: record.source_ref,
    reason_code: record.reason_code,
  };
}

function hasSecretReason(reasonCode: string): boolean {
  return /(?:SECRET|FORBIDDEN|SECURITY|PASSWORD|TOKEN|API[_-]?KEY|CREDENTIAL)/i.test(reasonCode);
}

export function isBox6SecretLikeMapping(mapping: Box6FieldMapping): boolean {
  return (
    hasSecretReason(mapping.reason_code) ||
    SECRET_LABEL_RE.test(mapping.target_label) ||
    SECRET_VALUE_RE.test(mapping.output_value)
  );
}

function isAllowedSecretPlaceholder(value: string): boolean {
  return UNFILLED_VALUES.has(value.trim());
}

function hasUnredactedSecretText(value: string): boolean {
  return !isAllowedSecretPlaceholder(value) && SECRET_VALUE_RE.test(value);
}

function renderedStrings(value: unknown): string[] {
  if (typeof value === 'string') return [value];
  if (Array.isArray(value)) return value.flatMap(renderedStrings);
  if (value && typeof value === 'object') {
    return Object.values(value as Record<string, unknown>).flatMap(renderedStrings);
  }
  return [];
}

export function hasBox6SecretAutofill(result: Box6FormFillResult): boolean {
  const unfilled = new Set(result.unfilled_fields.map(value => value.trim()));
  const reviewRequired = new Set(result.review_required.map(value => value.trim()));
  if (renderedStrings(result).some(hasUnredactedSecretText)) {
    return true;
  }
  return result.field_mappings.some(mapping => {
    const labelIsSecret = SECRET_LABEL_RE.test(mapping.target_label) || hasSecretReason(mapping.reason_code);
    if (labelIsSecret) {
      const safeUnfilled = isAllowedSecretPlaceholder(mapping.output_value) || mapping.confidence === 'UNFILLED';
      const topLevelReview = reviewRequired.has(mapping.target_label.trim()) || unfilled.has(mapping.target_label.trim());
      return !safeUnfilled || !topLevelReview;
    }
    return hasUnredactedSecretText(mapping.output_value);
  });
}

export function enforceBox6SecretGuard(result: Box6FormFillResult): void {
  if (hasBox6SecretAutofill(result)) {
    throw new Error(SECRET_GUARD_ERROR);
  }
}

export function validateBox6FormFillResult(value: unknown): Box6FormFillResult | null {
  if (!value || typeof value !== 'object') return null;
  const record = value as Record<string, unknown>;
  if (
    !hasExactKeys(record, RESULT_KEYS) ||
    record.schema_version !== 'card_06.form_fill.v1' ||
    typeof record.filled_form !== 'string' ||
    !Array.isArray(record.field_mappings)
  ) {
    return null;
  }
  const fieldMappings = record.field_mappings.map(validateMapping);
  if (fieldMappings.some(item => item === null)) return null;
  const unfilledFields = stringArray(record.unfilled_fields);
  const reviewRequired = stringArray(record.review_required);
  const warnings = stringArray(record.warnings);
  if (!unfilledFields || !reviewRequired || !warnings) return null;
  return {
    schema_version: 'card_06.form_fill.v1',
    filled_form: record.filled_form,
    field_mappings: fieldMappings as Box6FieldMapping[],
    unfilled_fields: unfilledFields,
    review_required: reviewRequired,
    warnings,
  };
}

export async function createBox6FormFill(request: Box6FormFillRequest): Promise<Box6FormFillResponse> {
  const blankForm = request.blankForm.trim();
  if (!blankForm) {
    throw new Error('빈 양식을 입력해 주세요.');
  }

  const prepared = await prepareCardTextFiles(request.files);
  const formData = new FormData();
  formData.append('query', blankForm);
  formData.append('card_mode', '6');
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
      throw new Error('BOX6_ANALYZE_STREAM_FAILED');
    }
    const body = await response.text();
    const result = parseAnalyzeStreamResult(body, validateBox6FormFillResult);
    enforceBox6SecretGuard(result);
    return { result, preparedFiles: prepared.files };
  } catch (error) {
    if (error instanceof Error && error.name === 'AbortError') throw error;
    if (error instanceof Error && error.message === SECRET_GUARD_ERROR) {
      throw new Error('보안 항목 자동기입이 감지되어 결과를 표시하지 않았습니다.');
    }
    if (error instanceof Error && error.message === 'BOX6_LEGACY_MAPPING_SCHEMA') {
      throw new Error('결과 형식을 확인하지 못했습니다.');
    }
    const message = uiSafeSidecarErrorMessage(error);
    if (message !== '요청 처리 중 오류가 발생했습니다. 잠시 후 다시 시도해 주세요.') {
      throw new Error(message);
    }
    throw error;
  }
}
