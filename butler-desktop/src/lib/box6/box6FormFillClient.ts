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

function stringArray(value: unknown): string[] | null {
  if (!Array.isArray(value)) return null;
  if (!value.every(item => typeof item === 'string')) return null;
  return value;
}

function validateMapping(value: unknown): Box6FieldMapping | null {
  if (!value || typeof value !== 'object') return null;
  const record = value as Record<string, unknown>;
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

export function validateBox6FormFillResult(value: unknown): Box6FormFillResult | null {
  if (!value || typeof value !== 'object') return null;
  const record = value as Record<string, unknown>;
  if (
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
    return {
      result: parseAnalyzeStreamResult(body, validateBox6FormFillResult),
      preparedFiles: prepared.files,
    };
  } catch (error) {
    if (error instanceof Error && error.name === 'AbortError') throw error;
    const message = uiSafeSidecarErrorMessage(error);
    if (message !== '요청 처리 중 오류가 발생했습니다. 잠시 후 다시 시도해 주세요.') {
      throw new Error(message);
    }
    throw error;
  }
}

