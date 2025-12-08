/**
 * Expo 앱 진입점
 * AccountingHUD 컴포넌트를 렌더링합니다.
 * 
 * @module app-expo/App
 */

import React from 'react';
import { View, StyleSheet } from 'react-native';
import { registerRootComponent } from 'expo';
import AccountingHUD from './src/ui/AccountingHUD';
import type { ClientCfg, Mode } from './src/hud/accounting-api';

const envMode = (process.env.EXPO_PUBLIC_DEMO_MODE === 'mock' ? 'mock' : 'live') as Mode;

const cfg: ClientCfg = {
  baseUrl: process.env.EXPO_PUBLIC_BFF_URL || 'http://localhost:8081',
  tenantId: process.env.EXPO_PUBLIC_TENANT_ID || 'default',
  apiKey: process.env.EXPO_PUBLIC_API_KEY || 'collector-key:operator',
  mode: envMode,
};

function App() {
  return (
    <View style={styles.root}>
      <AccountingHUD cfg={cfg} />
    </View>
  );
}

const styles = StyleSheet.create({
  root: {
    flex: 1,
  },
});

export default registerRootComponent(App);
