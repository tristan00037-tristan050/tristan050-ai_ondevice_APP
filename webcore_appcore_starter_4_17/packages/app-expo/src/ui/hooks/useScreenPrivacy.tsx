/**
 * 스크린 프라이버시 훅 및 컴포넌트
 * 
 * @module app-expo/ui/hooks/useScreenPrivacy
 */

import React, { useEffect, useState } from 'react';
// @ts-ignore - React Native types
import { AppState, AppStateStatus, View, StyleSheet, Platform } from 'react-native';

// 웹 환경에서는 expo 모듈을 사용하지 않음
// 웹 빌드 시 require가 문제를 일으킬 수 있으므로, 런타임에만 체크
let BlurView: any = null;
let ScreenCapture: any = null;

// 런타임에만 모듈 로드 시도 (빌드 타임에는 체크하지 않음)
const loadExpoModules = () => {
  if (typeof require !== 'undefined' && Platform.OS !== 'web') {
    try {
      // @ts-ignore - Expo types
      BlurView = require('expo-blur').BlurView;
      // @ts-ignore - Expo types
      ScreenCapture = require('expo-screen-capture');
    } catch (e) {
      // expo 모듈이 없으면 무시 (웹 환경 등)
    }
  }
};

export function useScreenPrivacy() {
  useEffect(() => {
    // 웹 환경에서는 실행하지 않음
    if (Platform.OS === 'web') {
      return;
    }

    // 런타임에 모듈 로드
    loadExpoModules();

    let mounted = true;
    (async () => {
      try {
        if (ScreenCapture?.preventScreenCaptureAsync) {
          await ScreenCapture.preventScreenCaptureAsync();
        }
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
        if (ScreenCapture?.allowScreenCaptureAsync) {
          ScreenCapture.allowScreenCaptureAsync().catch(() => {});
        }
        sub.remove();
      }
    };
  }, []);
}

export function ScreenPrivacyGate({ children }: { children: React.ReactNode }) {
  const [state, setState] = useState<AppStateStatus>(AppState.currentState);

  useEffect(() => {
    // 런타임에 모듈 로드
    loadExpoModules();
    
    const sub = AppState.addEventListener('change', setState as any);
    return () => {
      sub.remove();
    };
  }, []);

  const bg = state !== 'active';

  // 웹 환경에서는 BlurView 없이 children만 반환
  if (Platform.OS === 'web') {
    return <>{children}</>;
  }

  return (
    // @ts-expect-error - React Native JSX type compatibility issue with @types/react 18
    <View style={styles.flex}>
      {children}
      {/* @ts-expect-error - React Native JSX type compatibility issue with @types/react 18 */}
      {bg && BlurView ? <BlurView intensity={80} style={StyleSheet.absoluteFill} /> : null}
    </View>
  );
}

const styles = StyleSheet.create({ flex: { flex: 1 } });

