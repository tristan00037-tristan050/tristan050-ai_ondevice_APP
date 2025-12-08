/**
 * 엔진 모드 테스트
 * R8-S2: getEngineModeFromEnv + getSuggestEngine 조합 검증
 * 
 * @module app-expo/hud/engines/__tests__/engine-modes
 */

import { describe, it, expect, beforeEach, afterEach } from '@jest/globals';
import { getSuggestEngine } from '../index';
import { LocalLLMEngineV1 } from '../local-llm';
import { LocalRuleEngineV1Adapter } from '../index';
import type { ClientCfg } from '../../accounting-api';

describe('Engine Mode Selection', () => {
  const originalEnv = process.env;
  
  beforeEach(() => {
    // 각 테스트 전에 환경 변수 초기화
    jest.resetModules();
    process.env = { ...originalEnv };
  });
  
  afterEach(() => {
    // 각 테스트 후에 환경 변수 복원
    process.env = originalEnv;
  });

  const baseCfg: ClientCfg = {
    baseUrl: 'http://localhost:8081',
    tenantId: 'test-tenant',
    apiKey: 'test-key:operator',
  };

  describe('DEMO_MODE=mock', () => {
    it('should return mock engine regardless of ENGINE_MODE', () => {
      process.env.EXPO_PUBLIC_DEMO_MODE = 'mock';
      process.env.EXPO_PUBLIC_ENGINE_MODE = 'local-llm';
      
      const cfg: ClientCfg = { ...baseCfg, mode: 'mock' };
      const engine = getSuggestEngine(cfg);
      
      expect(engine.meta.type).toBe('mock');
      expect(engine).toBeInstanceOf(LocalRuleEngineV1Adapter);
      expect(engine.meta.label).toBe('Mock');
    });

    it('should return mock engine when ENGINE_MODE=remote', () => {
      process.env.EXPO_PUBLIC_DEMO_MODE = 'mock';
      process.env.EXPO_PUBLIC_ENGINE_MODE = 'remote';
      
      const cfg: ClientCfg = { ...baseCfg, mode: 'mock' };
      const engine = getSuggestEngine(cfg);
      
      expect(engine.meta.type).toBe('mock');
      expect(engine).toBeInstanceOf(LocalRuleEngineV1Adapter);
    });
  });

  describe('DEMO_MODE=live, ENGINE_MODE=local-llm', () => {
    it('should return LocalLLMEngineV1 instance', () => {
      process.env.EXPO_PUBLIC_DEMO_MODE = 'live';
      process.env.EXPO_PUBLIC_ENGINE_MODE = 'local-llm';
      
      const cfg: ClientCfg = { ...baseCfg, mode: 'live' };
      const engine = getSuggestEngine(cfg);
      
      expect(engine).toBeInstanceOf(LocalLLMEngineV1);
      expect(engine.meta.type).toBe('local-llm');
      expect(engine.meta.label).toBe('On-device LLM');
    });
  });

  describe('DEMO_MODE=live, ENGINE_MODE=rule', () => {
    it('should return LocalRuleEngineV1Adapter', () => {
      process.env.EXPO_PUBLIC_DEMO_MODE = 'live';
      process.env.EXPO_PUBLIC_ENGINE_MODE = 'rule';
      
      const cfg: ClientCfg = { ...baseCfg, mode: 'live' };
      const engine = getSuggestEngine(cfg);
      
      expect(engine).toBeInstanceOf(LocalRuleEngineV1Adapter);
      expect(engine.meta.type).toBe('rule');
      expect(engine.meta.label).toBe('On-device (Rule)');
    });
  });

  describe('DEMO_MODE=live, ENGINE_MODE=mock', () => {
    it('should return rule engine (mock mode only applies in demo mode)', () => {
      process.env.EXPO_PUBLIC_DEMO_MODE = 'live';
      process.env.EXPO_PUBLIC_ENGINE_MODE = 'mock';
      
      const cfg: ClientCfg = { ...baseCfg, mode: 'live' };
      const engine = getSuggestEngine(cfg);
      
      // Live 모드에서는 mock 엔진 모드가 rule로 처리됨
      expect(engine).toBeInstanceOf(LocalRuleEngineV1Adapter);
      expect(engine.meta.type).toBe('rule');
    });
  });

  describe('Default behavior', () => {
    it('should return rule engine when ENGINE_MODE is not set', () => {
      delete process.env.EXPO_PUBLIC_ENGINE_MODE;
      process.env.EXPO_PUBLIC_DEMO_MODE = 'live';
      
      const cfg: ClientCfg = { ...baseCfg, mode: 'live' };
      const engine = getSuggestEngine(cfg);
      
      expect(engine).toBeInstanceOf(LocalRuleEngineV1Adapter);
      expect(engine.meta.type).toBe('rule');
    });
  });
});

