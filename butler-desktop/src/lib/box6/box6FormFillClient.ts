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
  schema_version?: 'card_06.form_fill.v1';
  filled_form: string;
  field_mappings: Box6FieldMapping[];
  unfilled_fields: string[];
  review_required: boolean;
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

export function hasBox6SecretAutofill(result: Box6FormFillResult): boolean {
  const unfilled = new Set(result.unfilled_fields.map(value => value.trim()));
  return result.field_mappings.some(mapping => {
    const labelIsSecret = SECRET_LABEL_RE.test(mapping.target_label) || hasSecretReason(mapping.reason_code);
    if (labelIsSecret) {
      const safeUnfilled = isAllowedSecretPlaceholder(mapping.output_value) || mapping.confidence === 'UNFILLED';
      const topLevelReview = result.review_required === true || unfilled.has(mapping.target_label.trim());
      return !safeUnfilled || !topLevelReview;
    }
    return mapping.output_value.trim().length > 0 && SECRET_VALUE_RE.test(mapping.output_value);
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
    (record.schema_version !== undefined && record.schema_version !== 'card_06.form_fill.v1') ||
    typeof record.filled_form !== 'string' ||
    !Array.isArray(record.field_mappings) ||
    typeof record.review_required !== 'boolean'
  ) {
    return null;
  }
  const fieldMappings = record.field_mappings.map(validateMapping);
  if (fieldMappings.some(item => item === null)) return null;
  const unfilledFields = stringArray(record.unfilled_fields);
  const warnings = stringArray(record.warnings);
  if (!unfilledFields || !warnings) return null;
  return {
    schema_version: record.schema_version as 'card_06.form_fill.v1' | undefined,
    filled_form: record.filled_form,
    field_mappings: fieldMappings as Box6FieldMapping[],
    unfilled_fields: unfilledFields,
    review_required: record.review_required,
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
