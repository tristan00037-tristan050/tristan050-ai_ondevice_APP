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
    <View style={{ padding: 6, borderRadius: 12, backgroundColor: '#f0f0f0' }}>
      <Text>
        {`Offline Queue: ${count} • Last Sync: ${
          lastSyncTs ? new Date(lastSyncTs).toLocaleTimeString() : 'N/A'
        }`}
      </Text>
    </View>
  );
}

