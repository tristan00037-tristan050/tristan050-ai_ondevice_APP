/**
 * CS HUD 스켈레톤
 * R8-S1: 레이아웃과 네비게이션만 구성
 */

import React, { useState } from 'react';
import { View, Text, ScrollView, StyleSheet } from 'react-native';
import { getSuggestEngine } from '../hud/engines/index.js';
import type { ClientCfg as EnginesClientCfg } from '../hud/engines/index.js';
import type { ClientCfg } from '../hud/accounting-api.js';
import { isMock } from '../hud/accounting-api.js';

type Props = { cfg?: ClientCfg };

export function CsHUD({ cfg }: Props = {}) {
  const defaultCfg: ClientCfg = {
    baseUrl: process.env.EXPO_PUBLIC_BFF_URL || 'http://localhost:8081',
    tenantId: process.env.EXPO_PUBLIC_TENANT_ID || 'default',
    apiKey: process.env.EXPO_PUBLIC_API_KEY || 'collector-key:operator',
    mode: (process.env.EXPO_PUBLIC_DEMO_MODE === 'mock' ? 'mock' : 'live') as 'mock' | 'live',
  };
  
  const clientCfg = cfg || defaultCfg;
  
  // engines/index.ts의 ClientCfg로 변환
  const enginesCfg: EnginesClientCfg = {
    mode: clientCfg.mode || 'live',
    tenantId: clientCfg.tenantId,
    userId: 'hud-user-1',
    baseUrl: clientCfg.baseUrl,
    apiKey: clientCfg.apiKey,
  };
  
  const engine = getSuggestEngine(enginesCfg);
  const engineLabel = engine.id === 'local-llm-v1' 
    ? 'On-device (LLM Stub)' 
    : 'On-device (Rule)';

  return (
    <ScrollView style={styles.container}>
      <View style={styles.header}>
        <Text style={styles.title}>CS HUD (스켈레톤)</Text>
        <Text style={styles.engineLabel}>Engine: {engineLabel}</Text>
      </View>
      
      <View style={styles.content}>
        <Text style={styles.subtitle}>
          R8-S1 스프린트에서는 레이아웃과 네비게이션만 구성합니다.
        </Text>
        <Text style={styles.subtitle}>
          실제 CS 상담/티켓 워크플로우는 후속 스프린트에서 추가합니다.
        </Text>
        
        {isMock(clientCfg) && (
          <View style={styles.mockBanner}>
            <Text style={styles.mockText}>
              ⓘ Mock 모드: 네트워크 요청이 발생하지 않습니다.
            </Text>
          </View>
        )}
      </View>
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    padding: 16,
  },
  header: {
    marginBottom: 16,
  },
  title: {
    fontSize: 24,
    fontWeight: 'bold',
    color: '#333',
  },
  engineLabel: {
    fontSize: 12,
    color: '#666',
    marginTop: 4,
  },
  content: {
    marginTop: 16,
  },
  subtitle: {
    fontSize: 14,
    color: '#666',
    marginBottom: 8,
    lineHeight: 20,
  },
  mockBanner: {
    backgroundColor: '#fff3cd',
    padding: 12,
    borderRadius: 4,
    marginTop: 16,
    borderWidth: 1,
    borderColor: '#ffc107',
  },
  mockText: {
    fontSize: 12,
    color: '#856404',
  },
});

