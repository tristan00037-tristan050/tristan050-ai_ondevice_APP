/**
 * Why-Block Card Component
 * Leakage Firewall 차단 시 표시되는 카드 (reason_code만, 본문 0)
 */

import React from 'react';
// @ts-ignore - React Native types
import { View, Text } from 'react-native';

interface WhyBlockCardProps {
  reason_code: string;
}

export default function WhyBlockCard({ reason_code }: WhyBlockCardProps) {
  const reasonMessages: Record<string, string> = {
    'DUP_RATIO_EXCEEDED': '입력과 출력 간 중복률이 임계치를 초과했습니다',
    'CONTIGUOUS_LENGTH_EXCEEDED': '입력과 출력 간 연속 문자열 길이가 임계치를 초과했습니다',
  };

  const message = reasonMessages[reason_code] || '출력이 차단되었습니다';

  return (
    // @ts-expect-error - React Native JSX type compatibility issue with @types/react 18
    <View style={{
      backgroundColor: '#fee',
      padding: 12,
      borderRadius: 4,
      borderWidth: 1,
      borderColor: '#fcc',
      marginTop: 8,
    }}>
      {/* @ts-expect-error - React Native JSX type compatibility issue with @types/react 18 */}
      <Text style={{ color: '#c00', fontSize: 14, fontWeight: 'bold', marginBottom: 4 }}>
        ⚠️ 출력 차단
      </Text>
      {/* @ts-expect-error - React Native JSX type compatibility issue with @types/react 18 */}
      <Text style={{ color: '#666', fontSize: 12 }}>
        {message}
      </Text>
      {/* @ts-expect-error - React Native JSX type compatibility issue with @types/react 18 */}
      <Text style={{ color: '#999', fontSize: 10, marginTop: 4, fontFamily: 'monospace' }}>
        reason_code: {reason_code}
      </Text>
    </View>
  );
}

