/**
 * 온라인 상태 훅
 * 
 * @module app-expo/ui/hooks/useOnline
 */

import NetInfo from '@react-native-community/netinfo';
import { useEffect, useState } from 'react';

export function useOnline() {
  const [online, setOnline] = useState<boolean | null>(null);

  useEffect(() => {
    const sub = NetInfo.addEventListener((s) => setOnline(Boolean(s.isConnected)));
    return () => {
      sub();
    };
  }, []);

  return online;
}


