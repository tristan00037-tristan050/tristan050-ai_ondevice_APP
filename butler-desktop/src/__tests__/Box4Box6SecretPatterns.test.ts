import { describe, expect, it } from 'vitest';
import {
  SECRET_NEGATIVE_FIXTURES,
  SECRET_POSITIVE_FIXTURES,
  SECRET_TEXT_RE,
  containsSecretLikeText,
} from '../lib/cards/secretPatterns';
import { hasBox4SecretLeak, type Box4DocumentReviewResult } from '../lib/box4/box4ReviewClient';
import { hasBox6SecretAutofill, type Box6FormFillResult } from '../lib/box6/box6FormFillClient';

function box6With(path: 'filled_form' | 'output_value' | 'source_ref' | 'reason_code' | 'unfilled_fields' | 'warnings', value: string): Box6FormFillResult {
  const result: Box6FormFillResult = {
    schema_version: 'card_06.form_fill.v1',
    filled_form: '상호: 합성회사',
    field_mappings: [
      {
        target_label: '상호',
        output_value: '합성회사',
        confidence: 'HIGH',
        source_ref: 'attachment_digest_01',
        reason_code: 'LABEL_EXACT_MATCH',
      },
    ],
    unfilled_fields: [],
    review_required: [],
    warnings: [],
  };
  if (path === 'filled_form') result.filled_form = value;
  if (path === 'output_value') result.field_mappings[0].output_value = value;
  if (path === 'source_ref') result.field_mappings[0].source_ref = value;
  if (path === 'reason_code') result.field_mappings[0].reason_code = value;
  if (path === 'unfilled_fields') result.unfilled_fields = [value];
  if (path === 'warnings') result.warnings = [value];
  return result;
}

function box4With(path: 'summary' | 'warnings' | 'location' | 'original_text' | 'suggestion', value: string): Box4DocumentReviewResult {
  return {
    schema_version: 'card_04.document_review.v1',
    issues: [
      {
        location: path === 'location' ? value : '1문단',
        issue_type: 'STYLE',
        original_text: path === 'original_text' ? value : '문장 근거',
        suggestion: path === 'suggestion' ? value : '수정 제안',
        confidence: 'HIGH',
      },
    ],
    overall_score: 80,
    summary: path === 'summary' ? value : '요약',
    review_required: true,
    warnings: path === 'warnings' ? [value] : [],
    raw_log_zero: true,
    external_send_zero: true,
  };
}

describe('shared Box4/Box6 secret patterns', () => {
  it('blocks all positive fixtures and allows all negative fixtures', () => {
    expect(SECRET_POSITIVE_FIXTURES).toHaveLength(16);
    expect(SECRET_NEGATIVE_FIXTURES).toHaveLength(8);
    expect(SECRET_TEXT_RE.global).toBe(false);
    expect(SECRET_POSITIVE_FIXTURES.every(containsSecretLikeText)).toBe(true);
    expect(SECRET_NEGATIVE_FIXTURES.every(value => !containsSecretLikeText(value))).toBe(true);
  });

  it('does not hang on long non-secret input', () => {
    const text = '가'.repeat(100_000);
    expect(() => containsSecretLikeText(text)).not.toThrow();
  });

  it('scans Box6 six output paths', () => {
    for (const path of ['filled_form', 'output_value', 'source_ref', 'reason_code', 'unfilled_fields', 'warnings'] as const) {
      expect(hasBox6SecretAutofill(box6With(path, SECRET_POSITIVE_FIXTURES[0]))).toBe(true);
    }
  });

  it('allows Box6 secret labels only when unfilled and review-listed', () => {
    const allowed = box6With('output_value', 'UNFILLED');
    allowed.field_mappings[0].target_label = 'API 키';
    allowed.unfilled_fields = ['API 키'];
    expect(hasBox6SecretAutofill(allowed)).toBe(false);

    const blocked = box6With('output_value', '값 있음');
    blocked.field_mappings[0].target_label = 'API 키';
    expect(hasBox6SecretAutofill(blocked)).toBe(true);
  });

  it('scans Box4 five rendered output paths', () => {
    for (const path of ['summary', 'warnings', 'location', 'original_text', 'suggestion'] as const) {
      expect(hasBox4SecretLeak(box4With(path, SECRET_POSITIVE_FIXTURES[1]))).toBe(true);
    }
  });

  it('allows Box4 negative fixtures', () => {
    for (const value of SECRET_NEGATIVE_FIXTURES) {
      expect(hasBox4SecretLeak(box4With('summary', value))).toBe(false);
    }
  });
});
