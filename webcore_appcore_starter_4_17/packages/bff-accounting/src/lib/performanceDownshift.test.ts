/**
 * Performance Downshift with Hysteresis Tests
 * 
 * 채터링 방지 검증: 임계치 근처에서 과도한 토글 방지
 */

import { calculateDownshift, logDownshiftState } from './performanceDownshift';

describe('Performance Downshift with Hysteresis', () => {
  describe('Hysteresis prevents chattering', () => {
    it('should not toggle when latency oscillates around upward threshold', () => {
      // 시나리오: latency가 400ms 근처에서 진동 (L0 → L1 상향 임계치)
      let currentLevel = 0;

      // 400ms 초과 → L1로 증가
      let state = calculateDownshift(410, currentLevel);
      expect(state.downshift_level).toBe(1);
      expect(state.hysteresis_state).toBe('UPWARD');
      currentLevel = state.downshift_level;

      // 390ms로 떨어짐 (하향 임계치 150ms 미만이므로 L0으로 내려가지 않음)
      state = calculateDownshift(390, currentLevel);
      expect(state.downshift_level).toBe(1); // 유지
      expect(state.hysteresis_state).toBe('STABLE');

      // 405ms로 다시 상승 (여전히 L1 유지, 상향 임계치 600ms 미만)
      state = calculateDownshift(405, currentLevel);
      expect(state.downshift_level).toBe(1); // 유지
      expect(state.hysteresis_state).toBe('STABLE');

      // 150ms 이하로 떨어져야 L0으로 감소
      state = calculateDownshift(140, currentLevel);
      expect(state.downshift_level).toBe(0);
      expect(state.hysteresis_state).toBe('DOWNWARD');
    });

    it('should not toggle when latency oscillates around downward threshold', () => {
      // 시나리오: latency가 300ms 근처에서 진동 (L1 → L0 하향 임계치)
      let currentLevel = 1;

      // 150ms 이하 → L0으로 감소
      let state = calculateDownshift(140, currentLevel);
      expect(state.downshift_level).toBe(0);
      expect(state.hysteresis_state).toBe('DOWNWARD');
      currentLevel = state.downshift_level;

      // 160ms로 상승 (상향 임계치 400ms 미만이므로 L1로 올라가지 않음)
      state = calculateDownshift(160, currentLevel);
      expect(state.downshift_level).toBe(0); // 유지
      expect(state.hysteresis_state).toBe('STABLE');

      // 155ms로 다시 하락 (여전히 L0 유지)
      state = calculateDownshift(155, currentLevel);
      expect(state.downshift_level).toBe(0); // 유지
      expect(state.hysteresis_state).toBe('STABLE');

      // 400ms 이상으로 올라가야 L1로 증가
      state = calculateDownshift(410, currentLevel);
      expect(state.downshift_level).toBe(1);
      expect(state.hysteresis_state).toBe('UPWARD');
    });

    it('should prevent rapid toggling at L1-L2 boundary', () => {
      // 시나리오: L1-L2 경계에서 진동
      let currentLevel = 1;

      // 600ms 초과 → L2로 증가
      let state = calculateDownshift(610, currentLevel);
      expect(state.downshift_level).toBe(2);
      expect(state.hysteresis_state).toBe('UPWARD');
      currentLevel = state.downshift_level;

      // 590ms로 떨어짐 (하향 임계치 300ms 미만이므로 L1으로 내려가지 않음)
      state = calculateDownshift(590, currentLevel);
      expect(state.downshift_level).toBe(2); // 유지
      expect(state.hysteresis_state).toBe('STABLE');

      // 605ms로 다시 상승 (여전히 L2 유지)
      state = calculateDownshift(605, currentLevel);
      expect(state.downshift_level).toBe(2); // 유지
      expect(state.hysteresis_state).toBe('STABLE');

      // 300ms 이하로 떨어져야 L1으로 감소
      state = calculateDownshift(290, currentLevel);
      expect(state.downshift_level).toBe(1);
      expect(state.hysteresis_state).toBe('DOWNWARD');
    });
  });

  describe('Latency bucket classification', () => {
    it('should classify latency into correct buckets', () => {
      const testCases = [
        { latency: 150, expected: 'EXCELLENT' },
        { latency: 250, expected: 'GOOD' },
        { latency: 450, expected: 'FAIR' },
        { latency: 650, expected: 'POOR' },
        { latency: 850, expected: 'VERY_POOR' },
      ];

      testCases.forEach(({ latency, expected }) => {
        const state = calculateDownshift(latency, 0);
        expect(state.latency_bucket).toBe(expected);
      });
    });
  });

  describe('Budget limit enforcement (Fail-Closed)', () => {
    it('should enforce maximum downshift when budget exceeded', () => {
      // 예산 상한 1000ms 초과
      const state = calculateDownshift(1100, 0);
      expect(state.downshift_level).toBe(4); // 최대 다운시프트
      expect(state.hysteresis_state).toBe('UPWARD');
      expect(state.latency_bucket).toBe('VERY_POOR');
    });
  });

  describe('Deterministic behavior', () => {
    it('should produce identical results for identical inputs', () => {
      const state1 = calculateDownshift(450, 1);
      const state2 = calculateDownshift(450, 1);
      
      expect(state1.downshift_level).toBe(state2.downshift_level);
      expect(state1.latency_bucket).toBe(state2.latency_bucket);
      expect(state1.hysteresis_state).toBe(state2.hysteresis_state);
    });
  });

  describe('Meta-only output', () => {
    it('should only output meta-only fields', () => {
      const state = calculateDownshift(450, 1);
      
      // Meta-only 필드만 존재
      expect(state).toHaveProperty('downshift_level');
      expect(state).toHaveProperty('latency_bucket');
      expect(state).toHaveProperty('hysteresis_state');
      
      // 원문/본문 필드 없음
      expect(state).not.toHaveProperty('query');
      expect(state).not.toHaveProperty('text');
      expect(state).not.toHaveProperty('content');
      
      // 숫자/문자열만
      expect(typeof state.downshift_level).toBe('number');
      expect(typeof state.latency_bucket).toBe('string');
      expect(typeof state.hysteresis_state).toBe('string');
    });
  });
});

