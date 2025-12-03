/**
 * 스크린 프라이버시 훅 및 컴포넌트
 * 
 * @module app-expo/ui/hooks/useScreenPrivacy
 */

import { useEffect, useState } from 'react';
// @ts-ignore - React Native types
import { AppState, AppStateStatus, View, StyleSheet } from 'react-native';
// @ts-ignore - Expo types
import { BlurView } from 'expo-blur';
// @ts-ignore - Expo types
import * as ScreenCapture from 'expo-screen-capture';

export function useScreenPrivacy() {
  useEffect(() => {
    let mounted = true;
    (async () => {
      try {
        await ScreenCapture.preventScreenCaptureAsync();
      } catch {
        // ignore
      }
    })();

    const onChange = (s: AppStateStatus) => {
      // background시 블러는 컴포넌트로 처리
    };

    const sub = AppState.addEventListener('change', onChange);
    return () => {
      if (mounted) {
        ScreenCapture.allowScreenCaptureAsync().catch(() => {});
        sub.remove();
      }
    };
  }, []);
}

export function ScreenPrivacyGate({ children }: { children: React.ReactNode }) {
  const [state, setState] = useState<AppStateStatus>(AppState.currentState);

  useEffect(() => {
    const sub = AppState.addEventListener('change', setState as any);
    return () => {
      sub.remove();
    };
  }, []);

  const bg = state !== 'active';

  return (
    <View style={styles.flex}>
      {children}
      {bg ? <BlurView intensity={80} style={StyleSheet.absoluteFill} /> : null}
    </View>
  );
}

const styles = StyleSheet.create({ flex: { flex: 1 } });

