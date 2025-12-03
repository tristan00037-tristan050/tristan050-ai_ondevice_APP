/**
 * 리스크 스코어 엔진 인터페이스 및 플러그인 시스템
 * 
 * 목표: 규칙/스코어 기반에 리스크/이상탐지 엔진을 플러그인 형태로 결합하고,
 * 버저닝·A/B·롤백 가능
 * 
 * @module service-core-accounting/riskScoreEngine
 */

export type RiskInput = {
  tenant: string;
  ledgerEntry?: any;   // 도메인 타입으로 교체 예정
  externalTxn?: any;   // 도메인 타입으로 교체 예정
  context?: {
    actor?: string;
    requestId?: string;
    timestamp?: string;
  };
};

export type RiskResult = {
  score: number;        // 0.0 ~ 1.0 (높을수록 위험)
  reasons?: string[];   // 위험 요인 설명
  version: string;      // 엔진 버전
  metadata?: Record<string, any>;
};

export interface RiskScoreEngine {
  /**
   * 리스크 평가 수행
   */
  evaluate(input: RiskInput): Promise<RiskResult>;
  
  /**
   * 엔진 버전 반환
   */
  getVersion(): string;
}

/**
 * No-op 리스크 엔진 (기본값, 리스크 없음)
 */
export class NoopRiskScore implements RiskScoreEngine {
  readonly version = 'noop-0';

  async evaluate(input: RiskInput): Promise<RiskResult> {
    return {
      score: 0.0,
      reasons: ['noop engine - no risk'],
      version: this.version,
    };
  }

  getVersion(): string {
    return this.version;
  }
}

/**
 * 엔진 레지스트리 (향후 확장용)
 */
const engineRegistry: Map<string, () => RiskScoreEngine> = new Map();

export function registerRiskEngine(name: string, factory: () => RiskScoreEngine) {
  engineRegistry.set(name, factory);
}

export function resolveRiskEngine(name: string): RiskScoreEngine {
  const factory = engineRegistry.get(name);
  if (factory) {
    return factory();
  }
  // 기본값: NoopRiskScore
  return new NoopRiskScore();
}

/**
 * 환경변수 기반 엔진 리졸브
 */
export function getRiskEngine(): RiskScoreEngine {
  const engineName = process.env.RISK_ENGINE || 'noop';
  return resolveRiskEngine(engineName);
}

