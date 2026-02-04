/**
 * Expo 앱 진입점
 * AccountingHUD 컴포넌트를 렌더링합니다.
 * 
 * @module app-expo/App
 */

import React, { useState } from 'react';
import { View, StyleSheet, TouchableOpacity, Text } from 'react-native';
import { registerRootComponent } from 'expo';
import AccountingHUD from './src/ui/AccountingHUD';
import { CsHUD } from './src/ui/CsHUD';
import type { ClientCfg, Mode } from './src/hud/accounting-api';

const envMode = (process.env.EXPO_PUBLIC_DEMO_MODE === 'mock' ? 'mock' : 'live') as Mode;

const cfg: ClientCfg = {
  baseUrl: process.env.EXPO_PUBLIC_BFF_URL || 'http://localhost:8081',
  tenantId: process.env.EXPO_PUBLIC_TENANT_ID || 'default',
  apiKey: process.env.EXPO_PUBLIC_API_KEY || 'collector-key:operator',
  mode: envMode,
};

type HudMode = 'accounting' | 'cs';

function App() {
  const [mode, setMode] = useState<HudMode>('accounting');

  return (
    <View style={styles.root}>
      {/* 모드 토글 버튼 */}
      <View style={styles.toggleContainer}>
        <TouchableOpacity
          style={[styles.toggleButton, mode === 'accounting' && styles.toggleButtonActive]}
          onPress={() => setMode('accounting')}
        >
          <Text style={[styles.toggleText, mode === 'accounting' && styles.toggleTextActive]}>
            Accounting
          </Text>
        </TouchableOpacity>
        <TouchableOpacity
          style={[styles.toggleButton, mode === 'cs' && styles.toggleButtonActive]}
          onPress={() => setMode('cs')}
        >
          <Text style={[styles.toggleText, mode === 'cs' && styles.toggleTextActive]}>
            CS
          </Text>
        </TouchableOpacity>
      </View>

      {/* HUD 본문 */}
      <View style={styles.hudContainer}>
        {mode === 'accounting' ? <AccountingHUD cfg={cfg} /> : <CsHUD />}
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  root: {
    flex: 1,
  },
  toggleContainer: {
    flexDirection: 'row',
    backgroundColor: '#f5f5f5',
    padding: 8,
    borderBottomWidth: 1,
    borderBottomColor: '#ddd',
  },
  toggleButton: {
    flex: 1,
    padding: 12,
    alignItems: 'center',
    borderRadius: 4,
    marginHorizontal: 4,
  },
  toggleButtonActive: {
    backgroundColor: '#007AFF',
  },
  toggleText: {
    fontSize: 16,
    color: '#666',
    fontWeight: '500',
  },
  toggleTextActive: {
    color: '#fff',
    fontWeight: 'bold',
  },
  hudContainer: {
    flex: 1,
  },
});

export default registerRootComponent(App);
