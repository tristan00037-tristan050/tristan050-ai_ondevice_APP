/**
 * RiskScoreEngine v1 구현 (규칙 기반)
 * 
 * R8-S1: 고액 거래 리스크 필터
 * 
 * 규칙:
 * - 100만원 이상 → HIGH + ["HIGH_VALUE"]
 * - 50~100만원 → MEDIUM + ["MEDIUM_VALUE"]
 * - 모델 신뢰도 < 0.6 → 레벨 한 단계 상승 + ["LOW_CONFIDENCE"]
 * 
 * @module service-core-accounting/riskScoreEngineV1
 */

import { RiskScoreEngine, RiskScore, RiskLevel, RiskResult } from './riskScoreEngine.js';

export class RiskScoreEngineV1 implements RiskScoreEngine {
  readonly version = 'v1-rule-based';

  // 임계값 설정 (KRW 기준)
  private readonly HIGH_VALUE_THRESHOLD = 1_000_000;  // 100만원
  private readonly MEDIUM_VALUE_THRESHOLD = 500_000;   // 50만원
  private readonly LOW_CONFIDENCE_THRESHOLD = 0.6;     // 모델 신뢰도 0.6

  /**
   * Posting에 대한 리스크 평가
   */
  async scorePosting(input: {
    tenant: string;
    postingId: string;
    amount: number;
    currency: string;
    modelConfidence?: number;
    meta?: Record<string, unknown>;
  }): Promise<RiskScore> {
    const { tenant, postingId, amount, currency, modelConfidence } = input;
    
    // 통화별 환율 (간단 버전, 실제로는 환율 서비스 사용)
    const amountInKRW = this.convertToKRW(amount, currency);
    
    // 기본 레벨 및 이유 결정
    let level: RiskLevel = 'LOW';
    const reasons: string[] = [];
    let score = 0;

    // 금액 기반 규칙
    if (amountInKRW >= this.HIGH_VALUE_THRESHOLD) {
      level = 'HIGH';
      reasons.push('HIGH_VALUE');
      score = 80 + Math.min(20, (amountInKRW - this.HIGH_VALUE_THRESHOLD) / 100000);
    } else if (amountInKRW >= this.MEDIUM_VALUE_THRESHOLD) {
      level = 'MEDIUM';
      reasons.push('MEDIUM_VALUE');
      score = 40 + ((amountInKRW - this.MEDIUM_VALUE_THRESHOLD) / this.MEDIUM_VALUE_THRESHOLD) * 40;
    } else {
      level = 'LOW';
      score = (amountInKRW / this.MEDIUM_VALUE_THRESHOLD) * 40;
    }

    // 모델 신뢰도 기반 규칙
    if (modelConfidence !== undefined && modelConfidence < this.LOW_CONFIDENCE_THRESHOLD) {
      reasons.push('LOW_CONFIDENCE');
      // 레벨 한 단계 상승
      if (level === 'LOW') {
        level = 'MEDIUM';
        score = Math.max(score, 50);
      } else if (level === 'MEDIUM') {
        level = 'HIGH';
        score = Math.max(score, 70);
      }
    }

    // 점수 정규화 (0~100)
    score = Math.min(100, Math.max(0, Math.round(score)));

    return {
      posting_id: postingId,
      tenant,
      level,
      score,
      reasons,
      created_at: new Date(),
    };
  }

  /**
   * 통화를 KRW로 변환 (간단 버전)
   */
  private convertToKRW(amount: number, currency: string): number {
    // 실제로는 환율 서비스 사용
    const rates: Record<string, number> = {
      'KRW': 1,
      'USD': 1300,
      'EUR': 1400,
      'JPY': 9,
    };
    return amount * (rates[currency] || 1);
  }

  async evaluate(input: any): Promise<RiskResult> {
    // 기존 인터페이스 호환성
    return {
      score: 0.0,
      level: 'LOW',
      reason: 'Use scorePosting instead',
      reasons: [],
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
    const amountNum = typeof amount === 'string' ? parseFloat(amount) : amount;
    const riskScore = await this.scorePosting({
      tenant: 'default', // 임시
      postingId: 'temp',
      amount: amountNum,
      currency,
    });

    return {
      score: riskScore.score / 100, // 0~1로 변환
      level: riskScore.level,
      reason: riskScore.reasons.join(', '),
      reasons: riskScore.reasons,
      version: this.version,
    };
  }

  getVersion(): string {
    return this.version;
  }
}

