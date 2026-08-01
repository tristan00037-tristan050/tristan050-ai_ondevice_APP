import { describe, expect, it } from 'vitest';
import {
  parseLearningCapabilitySnapshot,
  selectLearningRows,
} from '../../lib/learningCapability';

describe('company learning capability additional regressions', () => {
  it('maps a canonical snapshot to exactly two in-use one registered-only and one preview-only row', () => {
    const snapshot = parseLearningCapabilitySnapshot({
      schema_version: 2,
      source: 'CANONICAL',
      snapshot_revision: 'b'.repeat(64),
      generation: 7,
      capabilities: {
        company_policy: 'IN_USE',
        company_fact: 'IN_USE',
        company_format: 'REGISTERED',
        folder_learning: 'NOT_REGISTERED',
      },
    });
    const rows = selectLearningRows(snapshot, 7);

    expect(rows.map(row => row.label)).toEqual([
      '회사 규칙 등록',
      '회사 사실 승인',
      '회사 양식 등록',
      '폴더에서 배우기',
    ]);
    expect(rows.filter(row => row.statusText === '사용 중')).toHaveLength(2);
    expect(rows.filter(row => row.statusText === '등록됨')).toHaveLength(1);
    expect(rows.filter(row => row.statusText === '등록되지 않음')).toHaveLength(1);
  });

  it('preserves a valid per-capability unavailable state without hiding healthy rows', () => {
    const snapshot = parseLearningCapabilitySnapshot({
      schema_version: 2,
      source: 'CANONICAL',
      snapshot_revision: 'c'.repeat(64),
      generation: 8,
      capabilities: {
        company_policy: 'IN_USE',
        company_fact: 'REGISTERED',
        company_format: 'UNAVAILABLE',
        folder_learning: 'NOT_REGISTERED',
      },
    });

    expect(selectLearningRows(snapshot).map(row => row.statusText)).toEqual([
      '사용 중',
      '등록됨',
      '확인할 수 없습니다',
      '등록되지 않음',
    ]);
  });

  it('maps unavailable or incomplete signals to four unknown rows without inference', () => {
    const unavailable = parseLearningCapabilitySnapshot({
      schema_version: 1,
      source: 'UNAVAILABLE',
      generation: 8,
      capabilities: {
        company_policy: 'IN_USE',
        company_fact: 'IN_USE',
        company_format: 'REGISTERED',
        folder_learning: 'NOT_REGISTERED',
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
