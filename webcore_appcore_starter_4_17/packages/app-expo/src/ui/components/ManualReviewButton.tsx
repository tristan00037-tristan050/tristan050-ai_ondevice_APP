import React from 'react';
import { Button, Alert } from 'react-native';
import { mkHeaders, isMock, type ClientCfg } from '../../hud/accounting-api';
import { guardEgressPayload, extractEgressAudit } from '../../egress/guard';

export default function ManualReviewButton({
  cfg,
  subjectType,
  subjectId,
  reason,
  reasonCode,
  amount,
  currency,
  isHighValue,
  onSuccess,
}: {
  cfg: ClientCfg;
  subjectType: string;
  subjectId: string;
  reason?: string;
  reasonCode?: string;
  amount?: number;
  currency?: string;
  isHighValue?: boolean;
  onSuccess?: () => void;
}) {
  const onPress = async () => {
    // Mock 모드에서는 실제 요청을 보내지 않음
    if (isMock(cfg)) {
      console.log('[MOCK] ManualReviewButton:', { subjectType, subjectId, reason, reasonCode, amount, currency, isHighValue });
      Alert.alert('수동 검토 요청이 접수되었습니다. (모의 / 서버 전송 없음)');
      onSuccess?.();
      return;
    }

    try {
      const headers = mkHeaders(cfg, {
        'Content-Type': 'application/json',
        'Idempotency-Key': crypto.randomUUID(),
      });
      
      const body: any = {
        subject_type: subjectType,
        subject_id: subjectId,
        reason,
      };
      
      // 추가 필드 포함
      if (reasonCode !== undefined) {
        body.reason_code = reasonCode;
      }
      if (amount !== undefined) {
        body.amount = amount;
      }
      if (currency !== undefined) {
        body.currency = currency;
      }
      if (isHighValue !== undefined) {
        body.is_high_value = isHighValue;
      }
      
      // Egress Guard v1: Live 모드에서 payload 검증 (Fail-Closed)
      const guardResult = guardEgressPayload(cfg, body);
      if (!guardResult.pass) {
        const audit = extractEgressAudit(guardResult);
        console.warn('[Egress Guard] Blocked:', audit);
        Alert.alert('요청 차단', `Egress Guard: ${guardResult.reason_code}`);
        return;
      }
      
      const r = await fetch(`${cfg.baseUrl}/v1/accounting/audit/manual-review`, {
        method: 'POST',
        headers,
        body: JSON.stringify(body),
      });
      if (r.ok) {
        onSuccess?.();
        // Alert는 호출하지 않고, 상위 컴포넌트에서 메시지 표시
      } else {
        const text = await r.text();
        Alert.alert('요청 실패', text);
      }
    } catch (e: any) {
      Alert.alert('오류', e.message || String(e));
    }
  };

  // @ts-expect-error - React Native JSX type compatibility issue with @types/react 18
  return <Button title="수동 검토 요청" onPress={onPress} />;
}

