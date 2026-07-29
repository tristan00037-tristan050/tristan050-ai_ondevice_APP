import { describe, expect, it } from 'vitest';
import {
  parseLearningCapabilitySnapshot,
  selectLearningRows,
} from '../../lib/learningCapability';

describe('company learning capability selector', () => {
  it('parses the real provider contract and rejects incompatible v8 rows payload', () => {
    const canonical = parseLearningCapabilitySnapshot({
      schema_version: 2,
      source: 'CANONICAL',
      snapshot_revision: 'a'.repeat(64),
      generation: 11,
      capabilities: {
        company_policy: 'IN_USE',
        company_fact: 'IN_USE',
        company_format: 'REGISTERED',
        folder_learning: 'NOT_REGISTERED',
      },
    });
    const incompatible = parseLearningCapabilitySnapshot({
      schema_version: 'learning_capability.v1',
      source: 'CANONICAL',
      generation: 11,
      rows: [{ key: 'company_policy', state: 'IN_USE' }],
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
          company_policy: 'IN_USE',
          company_fact: 'IN_USE',
          company_format: 'REGISTERED',
        },
      },
      {
        schema_version: 1,
        source: 'CANONICAL',
        generation: 1,
        capabilities: {
          company_policy: 'IN_USE',
          company_fact: 'UNKNOWN',
          company_format: 'REGISTERED',
          folder_learning: 'NOT_REGISTERED',
        },
      },
      {
        schema_version: 1,
        source: 'CANONICAL',
        generation: true,
        capabilities: {
          company_policy: 'IN_USE',
          company_fact: 'IN_USE',
          company_format: 'REGISTERED',
          folder_learning: 'NOT_REGISTERED',
        },
      },
    ];
    for (const failure of failures) {
      const rows = selectLearningRows(parseLearningCapabilitySnapshot(failure));
      expect(rows).toHaveLength(4);
      expect(rows.every(row => row.statusText === '확인할 수 없습니다')).toBe(true);
    }
  });

});
