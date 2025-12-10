/**
 * CS HUD
 * R8-S1: 레이아웃과 네비게이션만 구성
 * R9-S1: CS 티켓 리스트 API 연동
 */

import React, { useState, useEffect } from 'react';
import { View, Text, ScrollView, StyleSheet, FlatList, ActivityIndicator } from 'react-native';
import { getSuggestEngine } from '../hud/engines/index';
import type { ClientCfg as EnginesClientCfg } from '../hud/engines/index';
import type { ClientCfg } from '../hud/accounting-api';
import { isMock } from '../hud/accounting-api';
import { fetchCsTickets, type CsTicket } from '../hud/cs-api';

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

  // 티켓 리스트 상태
  const [tickets, setTickets] = useState<CsTicket[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // 티켓 리스트 로드
  useEffect(() => {
    let cancelled = false;

    async function loadTickets() {
      try {
        setLoading(true);
        setError(null);

        const response = await fetchCsTickets(clientCfg, {
          limit: 20,
          offset: 0,
        });

        if (!cancelled) {
          setTickets(response.items);
          setLoading(false);
        }
      } catch (err: any) {
        if (!cancelled) {
          console.error('[CsHUD] Failed to load tickets:', err);
          setError(err.message || '티켓을 불러오는데 실패했습니다.');
          setLoading(false);
        }
      }
    }

    loadTickets();

    return () => {
      cancelled = true;
    };
  }, [clientCfg]);

  const renderTicket = ({ item }: { item: CsTicket }) => {
    const statusColor = item.status === 'open' ? '#28a745' : item.status === 'pending' ? '#ffc107' : '#6c757d';
    const statusText = item.status === 'open' ? '열림' : item.status === 'pending' ? '대기' : '닫힘';
    const createdAt = new Date(item.createdAt).toLocaleDateString('ko-KR');

    return (
      <View style={styles.ticketItem}>
        <View style={styles.ticketHeader}>
          <Text style={styles.ticketSubject}>{item.subject}</Text>
          <View style={[styles.statusBadge, { backgroundColor: statusColor }]}>
            <Text style={styles.statusText}>{statusText}</Text>
          </View>
        </View>
        <Text style={styles.ticketDate}>생성일: {createdAt}</Text>
      </View>
    );
  };

  return (
    <ScrollView style={styles.container}>
      <View style={styles.header}>
        <Text style={styles.title}>CS HUD</Text>
        <Text style={styles.engineLabel}>Engine: {engineLabel}</Text>
      </View>
      
      {isMock(clientCfg) && (
        <View style={styles.mockBanner}>
          <Text style={styles.mockText}>
            ⓘ Mock 모드: 네트워크 요청이 발생하지 않습니다.
          </Text>
        </View>
      )}

      <View style={styles.content}>
        <Text style={styles.sectionTitle}>최근 티켓</Text>
        
        {loading && (
          <View style={styles.centerContainer}>
            <ActivityIndicator size="small" color="#007AFF" />
            <Text style={styles.loadingText}>불러오는 중...</Text>
          </View>
        )}

        {error && (
          <View style={styles.errorContainer}>
            <Text style={styles.errorText}>❌ {error}</Text>
          </View>
        )}

        {!loading && !error && tickets.length === 0 && (
          <View style={styles.centerContainer}>
            <Text style={styles.emptyText}>티켓이 없습니다.</Text>
          </View>
        )}

        {!loading && !error && tickets.length > 0 && (
          <FlatList
            data={tickets}
            renderItem={renderTicket}
            keyExtractor={(item) => String(item.id)}
            scrollEnabled={false}
            style={styles.ticketList}
          />
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
  sectionTitle: {
    fontSize: 18,
    fontWeight: '600',
    color: '#333',
    marginBottom: 12,
  },
  mockBanner: {
    backgroundColor: '#fff3cd',
    padding: 12,
    borderRadius: 4,
    marginTop: 16,
    marginBottom: 16,
    borderWidth: 1,
    borderColor: '#ffc107',
  },
  mockText: {
    fontSize: 12,
    color: '#856404',
  },
  centerContainer: {
    alignItems: 'center',
    justifyContent: 'center',
    padding: 32,
  },
  loadingText: {
    marginTop: 8,
    fontSize: 14,
    color: '#666',
  },
  errorContainer: {
    backgroundColor: '#f8d7da',
    padding: 12,
    borderRadius: 4,
    borderWidth: 1,
    borderColor: '#f5c6cb',
  },
  errorText: {
    fontSize: 14,
    color: '#721c24',
  },
  emptyText: {
    fontSize: 14,
    color: '#666',
    fontStyle: 'italic',
  },
  ticketList: {
    marginTop: 8,
  },
  ticketItem: {
    backgroundColor: '#f8f9fa',
    padding: 12,
    borderRadius: 4,
    marginBottom: 8,
    borderWidth: 1,
    borderColor: '#dee2e6',
  },
  ticketHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: 4,
  },
  ticketSubject: {
    fontSize: 16,
    fontWeight: '500',
    color: '#333',
    flex: 1,
    marginRight: 8,
  },
  statusBadge: {
    paddingHorizontal: 8,
    paddingVertical: 4,
    borderRadius: 12,
  },
  statusText: {
    fontSize: 12,
    color: '#fff',
    fontWeight: '600',
  },
  ticketDate: {
    fontSize: 12,
    color: '#666',
    marginTop: 4,
  },
});

