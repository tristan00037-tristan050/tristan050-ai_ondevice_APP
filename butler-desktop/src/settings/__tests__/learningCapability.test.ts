import { describe, expect, it } from 'vitest';
import {
  parseLearningCapabilitySnapshot,
  selectLearningRows,
} from '../../lib/learningCapability';

describe('company learning capability selector', () => {
  it('parses the real provider contract and rejects incompatible v8 rows payload', () => {
    const canonical = parseLearningCapabilitySnapshot({
      schema_version: 1,
      source: 'CANONICAL',
      generation: 11,
      capabilities: {
        company_rules: 'IN_USE',
        company_facts: 'IN_USE',
        company_formats: 'REGISTERED_ONLY',
        folder_learning: 'PREVIEW_ONLY',
      },
    });
    const incompatible = parseLearningCapabilitySnapshot({
      schema_version: 'learning_capability.v1',
      source: 'CANONICAL',
      generation: 11,
      rows: [{ key: 'company_rules', state: 'IN_USE' }],
    });

    expect(canonical.source).toBe('CANONICAL_CAPABILITY');
    expect(incompatible.source).toBe('UNAVAILABLE');
    expect(selectLearningRows(incompatible).every(
      row => row.statusText === '확인할 수 없습니다',
    )).toBe(true);
  });

  it('keeps all four rows unknown for every unavailable transport and schema failure', () => {
    const failures = [
      null,
      { schema_version: 1, source: 'UNAVAILABLE', reason: 'AUTHORITY_INCOMPLETE' },
      { schema_version: 1, source: 'CANONICAL', generation: -1, capabilities: {} },
      {
        schema_version: 1,
        source: 'CANONICAL',
        generation: 1,
        capabilities: {
          company_rules: 'IN_USE',
          company_facts: 'IN_USE',
          company_formats: 'REGISTERED_ONLY',
        },
      },
    ];
    for (const failure of failures) {
      const rows = selectLearningRows(parseLearningCapabilitySnapshot(failure));
      expect(rows).toHaveLength(4);
      expect(rows.every(row => row.statusText === '확인할 수 없습니다')).toBe(true);
    }
  });

  it('maps a canonical snapshot to exactly two in-use one registered-only and one preview-only row', () => {
    const snapshot = parseLearningCapabilitySnapshot({
      schema_version: 1,
      source: 'CANONICAL',
      generation: 7,
      capabilities: {
        company_rules: 'IN_USE',
        company_facts: 'IN_USE',
        company_formats: 'REGISTERED_ONLY',
        folder_learning: 'PREVIEW_ONLY',
      },
    });
    const rows = selectLearningRows(snapshot, 7);

    expect(rows.map(row => row.label)).toEqual([
      '회사 규칙 등록',
      '회사 사실 승인',
      '회사 양식 등록',
      '폴더에서 배우기',
    ]);
    expect(rows.filter(row => row.statusText === '쓰이는 중')).toHaveLength(2);
    expect(rows.filter(row => row.statusText === '등록만 됩니다')).toHaveLength(1);
    expect(rows.filter(row => row.statusText === '미리보기만 됩니다')).toHaveLength(1);
  });

  it('maps unavailable or incomplete signals to four unknown rows without inference', () => {
    const unavailable = parseLearningCapabilitySnapshot({
      schema_version: 1,
      source: 'UNAVAILABLE',
      generation: 8,
      capabilities: {
        company_rules: 'IN_USE',
        company_facts: 'IN_USE',
        company_formats: 'REGISTERED_ONLY',
        folder_learning: 'PREVIEW_ONLY',
      },
    });
    const incomplete = parseLearningCapabilitySnapshot({
      schema_version: 1,
      source: 'CANONICAL',
      generation: 9,
      capabilities: {},
    });

    expect(selectLearningRows(unavailable)).toHaveLength(4);
    expect(selectLearningRows(unavailable).every(
      row => row.statusText === '확인할 수 없습니다',
    )).toBe(true);
    expect(selectLearningRows(incomplete).every(
      row => row.statusText === '확인할 수 없습니다',
    )).toBe(true);
  });
});
