/**
 * CS HUD 스켈레톤
 * R8-S1: 레이아웃과 네비게이션만 구성
 */

import React from 'react';
import { View, Text, ScrollView, StyleSheet } from 'react-native';

export function CsHUD() {
  return (
    <ScrollView style={styles.container}>
      <View style={styles.header}>
        <Text style={styles.title}>CS HUD (스켈레톤)</Text>
      </View>
      
      <View style={styles.content}>
        <Text style={styles.subtitle}>
          R8-S1 스프린트에서는 레이아웃과 네비게이션만 구성합니다.
        </Text>
        <Text style={styles.subtitle}>
          실제 CS 상담/티켓 워크플로우는 후속 스프린트에서 추가합니다.
        </Text>
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
  content: {
    marginTop: 16,
  },
  subtitle: {
    fontSize: 14,
    color: '#666',
    marginBottom: 8,
    lineHeight: 20,
  },
});

