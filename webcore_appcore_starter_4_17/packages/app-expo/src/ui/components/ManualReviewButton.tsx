import React from 'react';
import { Button, Alert } from 'react-native';
import { mkHeaders, type ClientCfg } from '../../hud/accounting-api.js';

export default function ManualReviewButton({
  cfg,
  subjectType,
  subjectId,
  reason,
  reasonCode,
  amount,
  currency,
  isHighValue,
}: {
  cfg: ClientCfg;
  subjectType: string;
  subjectId: string;
  reason?: string;
  reasonCode?: string;
  amount?: number;
  currency?: string;
  isHighValue?: boolean;
}) {
  const onPress = async () => {
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
      
      const r = await fetch(`${cfg.baseUrl}/v1/accounting/audit/manual-review`, {
        method: 'POST',
        headers,
        body: JSON.stringify(body),
      });
      if (r.ok) {
        Alert.alert('수동 검토 요청이 접수되었습니다.');
      } else {
        const text = await r.text();
        Alert.alert('요청 실패', text);
      }
    } catch (e: any) {
      Alert.alert('오류', e.message || String(e));
    }
  };

  return <Button title="수동 검토 요청" onPress={onPress} />;
}

