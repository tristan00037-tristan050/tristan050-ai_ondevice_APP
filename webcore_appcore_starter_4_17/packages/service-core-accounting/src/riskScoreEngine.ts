/**
 * 리스크 스코어 엔진 인터페이스 및 플러그인 시스템
 * 
 * 목표: 규칙/스코어 기반에 리스크/이상탐지 엔진을 플러그인 형태로 결합하고,
 * 버저닝·A/B·롤백 가능
 * 
 * @module service-core-accounting/riskScoreEngine
 * 
 * @overview R8-S1 v1 스코프
 * 
 * R8-S1에서는 "고액 거래 리스크 필터"에 한정하여 구현합니다.
 * 
 * 입력:
 * - 금액 (amount): 거래 금액
 * - 통화 (currency): 통화 코드 (예: 'KRW', 'USD')
 * - actor: 요청자 식별자
 * - merchant: 거래 상대방/가맹점 정보
 * - 과거 ManualReview 이력: 동일 actor/merchant의 과거 수동 검토 이력
 * 
 * 출력:
 * - score: 리스크 점수 (0.0 ~ 1.0, 높을수록 위험)
 * - level: 리스크 레벨 ('LOW' | 'MEDIUM' | 'HIGH')
 * - reason: 리스크 판단 근거 설명
 * 
 * 향후 확장:
 * - R8-S2: 이상 패턴 탐지 (빈도, 시간대, 금액 분포 등)
 * - R8-S3: 머신러닝 기반 리스크 모델
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
  level: 'LOW' | 'MEDIUM' | 'HIGH';  // 리스크 레벨
  reason: string;      // 위험 판단 근거 설명
  reasons?: string[];   // 위험 요인 설명 (하위 호환성)
  version: string;      // 엔진 버전
  metadata?: Record<string, any>;
};

export interface RiskScoreEngine {
  /**
   * 리스크 평가 수행 (일반)
   */
  evaluate(input: RiskInput): Promise<RiskResult>;
  
  /**
   * 고액 거래 리스크 평가 (R8-S1 v1)
   * 
   * 고액 거래에 대한 리스크를 평가합니다.
   * 
   * @param amount - 거래 금액 (숫자 또는 문자열)
   * @param currency - 통화 코드 (예: 'KRW', 'USD')
   * @param actor - 요청자 식별자
   * @param merchant - 거래 상대방/가맹점 정보 (선택)
   * @param manualReviewHistory - 과거 ManualReview 이력 (선택)
   * @returns 리스크 평가 결과
   */
  evaluateHighValueTxn(
    amount: number | string,
    currency: string,
    actor: string,
    merchant?: string,
    manualReviewHistory?: Array<{ ts: string; amount: number | string; reason?: string }>
  ): Promise<RiskResult>;
  
  /**
   * 엔진 버전 반환
   */
  getVersion(): string;
}

/**
 * No-op 리스크 엔진 (기본값, 리스크 없음)
 * 
 * R8-S1 구현 전까지는 모든 거래를 LOW 리스크로 처리합니다.
 */
export class NoopRiskScore implements RiskScoreEngine {
  readonly version = 'noop-0';

  async evaluate(input: RiskInput): Promise<RiskResult> {
    return {
      score: 0.0,
      level: 'LOW',
      reason: 'noop engine - no risk',
      reasons: ['noop engine - no risk'],
      version: this.version,
    };
  }

  async evaluateHighValueTxn(
    amount: number | string,
    currency: string,
    actor: string,
    merchant?: string,
    manualReviewHistory?: Array<{ ts: string; amount: number | string; reason?: string }>
  ): Promise<RiskResult> {
    // R8-S1 구현 전까지는 항상 LOW 리스크 반환
    return {
      score: 0.0,
      level: 'LOW',
      reason: 'noop engine - no risk (R8-S1 구현 대기)',
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

