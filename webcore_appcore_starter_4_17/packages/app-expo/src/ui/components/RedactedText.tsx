/**
 * 마스킹 토글 컴포넌트
 * 
 * @module app-expo/ui/components/RedactedText
 */

import { useState } from 'react';
// @ts-ignore - React Native types
import { Text, Pressable } from 'react-native';

export function RedactedText({ value, masked = true }: { value: string; masked?: boolean }) {
  const [show, setShow] = useState(!masked);
  const display = show ? value : value.replace(/./g, '•');

  return (
    // @ts-expect-error - React Native JSX type compatibility issue with @types/react 18
    <Pressable onPress={() => setShow((s) => !s)}>
      {/* @ts-expect-error - React Native JSX type compatibility issue with @types/react 18 */}
      <Text>
        {display} {show ? '🙈' : '👁️'}
      </Text>
    </Pressable>
  );
}

