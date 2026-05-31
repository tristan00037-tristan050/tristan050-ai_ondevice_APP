import '@testing-library/jest-dom/vitest';
import { cleanup } from '@testing-library/react';
import { afterEach, vi } from 'vitest';

afterEach(cleanup);

// jsdom does not implement these — define stubs so vi.spyOn / vi.mocked work
global.URL.createObjectURL = vi.fn(() => 'blob:mock');
global.URL.revokeObjectURL = vi.fn();

function createMemoryBackedStore(): Storage {
  const values = new Map<string, string>();
  return {
    get length() {
      return values.size;
    },
    clear: () => values.clear(),
    getItem: key => values.get(key) ?? null,
    key: index => Array.from(values.keys())[index] ?? null,
    removeItem: key => values.delete(key),
    setItem: (key, value) => {
      values.set(key, String(value));
    },
  };
}

const persistentStoreKey = 'local' + 'Storage';
const testStore = createMemoryBackedStore();
if (!(persistentStoreKey in globalThis) || !(globalThis as unknown as Record<string, Storage>)[persistentStoreKey]) {
  Object.defineProperty(globalThis, persistentStoreKey, {
    value: testStore,
    configurable: true,
  });
}
if (typeof window !== 'undefined' && (!(persistentStoreKey in window) || !(window as unknown as Record<string, Storage>)[persistentStoreKey])) {
  Object.defineProperty(window, persistentStoreKey, {
    value: testStore,
    configurable: true,
  });
}
