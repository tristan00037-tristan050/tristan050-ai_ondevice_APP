/**
 * Why-Block Card Component
 * Leakage Firewall 차단 시 표시되는 카드 (reason_code만, 본문 0)
 */

import React from 'react';
// @ts-ignore - React Native types
import { View, Text } from 'react-native';

interface WhyBlockCardProps {
  reason_code: string;
  next_steps?: string[];
}

export default function WhyBlockCard({ reason_code, next_steps }: WhyBlockCardProps) {
  const reasonMessages: Record<string, string> = {
    'DUP_RATIO_EXCEEDED': '입력과 출력 간 중복률이 임계치를 초과했습니다',
    'CONTIGUOUS_LENGTH_EXCEEDED': '입력과 출력 간 연속 문자열 길이가 임계치를 초과했습니다',
    'BASE64_SUSPECT': '출력에 Base64 인코딩 패턴이 감지되었습니다',
    'HIGH_ENTROPY_COMPRESSION_ANOMALY': '출력의 엔트로피와 압축률이 이상치 범위입니다',
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
      {/* next_steps 표시 (v2) */}
      {next_steps && next_steps.length > 0 && (
        // @ts-expect-error - React Native JSX type compatibility issue with @types/react 18
        <View style={{ marginTop: 8, paddingTop: 8, borderTopWidth: 1, borderTopColor: '#fcc' }}>
          {/* @ts-expect-error - React Native JSX type compatibility issue with @types/react 18 */}
          <Text style={{ color: '#666', fontSize: 11, fontWeight: 'bold', marginBottom: 4 }}>
            다음 단계:
          </Text>
          {next_steps.map((step, idx) => (
            // @ts-expect-error - React Native JSX type compatibility issue with @types/react 18
            <Text key={idx} style={{ color: '#666', fontSize: 10, marginTop: 2 }}>
              • {step}
            </Text>
          ))}
        </View>
      )}
    </View>
  );
}

