import React from 'react';
import { View, Text } from 'react-native';

export default function QueueBadge({
  count = 0,
  lastSyncTs,
}: {
  count: number;
  lastSyncTs?: number;
}) {
  return (
    // @ts-expect-error - React Native JSX type compatibility issue with @types/react 18
    <View style={{ padding: 6, borderRadius: 12, backgroundColor: '#f0f0f0' }}>
      {/* @ts-expect-error - React Native JSX type compatibility issue with @types/react 18 */}
      <Text>
        {`Offline Queue: ${count} • Last Sync: ${
          lastSyncTs ? new Date(lastSyncTs).toLocaleTimeString() : 'N/A'
        }`}
      </Text>
    </View>
  );
}

