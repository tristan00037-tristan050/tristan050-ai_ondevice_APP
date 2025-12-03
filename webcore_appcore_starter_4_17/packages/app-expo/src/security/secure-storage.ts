/**
 * 암호화 스토리지 (AES-GCM)
 * 키는 SecureStore, 데이터는 MMKV
 * 
 * @module app-expo/security/secure-storage
 * 
 * Note: 이 모듈은 React Native/Expo 환경에서 실행됩니다.
 * Node.js 빌드 환경에서는 타입 체크만 수행하며, 실제 구현은 런타임에서 동적 import됩니다.
 */

// 타입 정의 (빌드 시점 타입 체크용)
// React Native/Expo 모듈은 런타임에서만 사용 가능하므로 타입만 import
type SecureStoreType = typeof import('expo-secure-store');
type MMKVType = typeof import('react-native-mmkv');
type RandomType = typeof import('expo-random');

type Bytes = Uint8Array;

// 런타임에서 동적으로 로드 (React Native 환경)
// Node.js 빌드 환경에서는 타입 체크만 수행
let SecureStore: SecureStoreType | null = null;
let MMKV: MMKVType['MMKV'] | null = null;
let Random: RandomType | null = null;

async function ensureModules(): Promise<void> {
  if (SecureStore && MMKV && Random) {
    return;
  }
  
  // 동적 import는 React Native 런타임에서만 가능
  // 빌드 시점에는 타입만 체크
  try {
    SecureStore = await import('expo-secure-store');
    const MMKVModule = await import('react-native-mmkv');
    MMKV = MMKVModule.MMKV;
    Random = await import('expo-random');
  } catch {
    // Node.js 빌드 환경에서는 모듈을 찾을 수 없음 (정상)
    // 실제 런타임에서는 React Native 환경에서만 실행됨
  }
}

async function getOrCreateKey(): Promise<string> {
  await ensureModules();
  if (!SecureStore) {
    throw new Error('SecureStore not available in this environment');
  }
  
  const keyId = 'appcore.kek.v1';
  let key: string | null = await SecureStore.getItemAsync(keyId);
  
  if (!key) {
    if (!Random) {
      throw new Error('Random not available in this environment');
    }
    const bytes = await Random.getRandomBytesAsync(32);
    // Base64url
    key = Buffer.from(bytes).toString('base64url');
    if (!key) {
      throw new Error('Failed to generate key');
    }
    await SecureStore.setItemAsync(keyId, key, {
      keychainAccessible: SecureStore.AFTER_FIRST_UNLOCK_THIS_DEVICE_ONLY,
    });
  }
  
  if (!key) {
    throw new Error('Failed to get or create key');
  }
  
  return key;
}

// MMKV는 자체 암호화 옵션이 있지만, 키 회전/교체를 제어하기 위해
// SecureStore에 보관된 KEK로 MMKV encryptionKey를 설정
let _mmkv: any = null;

export async function getSecureKV(): Promise<any> {
  await ensureModules();
  if (!MMKV) {
    throw new Error('MMKV not available in this environment');
  }
  
  if (_mmkv) {
    return _mmkv;
  }
  
  const kek = await getOrCreateKey();
  // @ts-ignore - MMKV 생성자는 런타임에서만 사용 가능
  _mmkv = new MMKV({ id: 'appcore.secure', encryptionKey: kek });
  return _mmkv;
}

// AES-GCM 구현: RN 0.72+ 환경에서는 WebCrypto가 점진 지원되지만,
// 여기서는 간단히 브라우저 SubtleCrypto 유무를 확인하고,
// 없으면 예외를 던집니다(빌드 시점: Expo SDK ≥50 권장).
function subtle(): SubtleCrypto {
  // @ts-ignore
  const sc: SubtleCrypto | undefined = globalThis.crypto?.subtle ?? undefined;
  if (!sc) {
    throw new Error('WebCrypto SubtleCrypto unavailable. Use Expo SDK 50+ or polyfill.');
  }
  return sc!;
}

async function importKey(rawKey: Bytes): Promise<CryptoKey> {
  // BufferSource로 변환 (ArrayBuffer 또는 ArrayBufferView)
  // Uint8Array는 이미 BufferSource이므로 타입 캐스팅으로 해결
  return await subtle().importKey(
    'raw',
    rawKey as unknown as BufferSource,
    { name: 'AES-GCM' },
    false,
    ['encrypt', 'decrypt']
  );
}

function b64uToBytes(s: string): Bytes {
  return new Uint8Array(Buffer.from(s, 'base64url'));
}

function bytesToB64u(b: Bytes): string {
  return Buffer.from(b).toString('base64url');
}

/**
 * 암호화된 보고서 저장
 * 
 * @param id - 보고서 ID
 * @param payload - 저장할 데이터
 */
export async function saveEncryptedReport(id: string, payload: unknown): Promise<void> {
  const kv = await getSecureKV();
  const kek = await getOrCreateKey();
  const key = await importKey(b64uToBytes(kek));
  
  if (!Random) {
    throw new Error('Random not available in this environment');
  }
  const iv = await Random.getRandomBytesAsync(12);
  const data = new TextEncoder().encode(JSON.stringify(payload));
  
  const ct = new Uint8Array(await subtle().encrypt({ name: 'AES-GCM', iv: iv as unknown as BufferSource }, key, data));
  
  const bundle = JSON.stringify({
    v: 1,
    iv: bytesToB64u(iv),
    ct: bytesToB64u(ct),
  });
  
  kv.set(`report:${id}`, bundle);
}

/**
 * 암호화된 보고서 로드
 * 
 * @param id - 보고서 ID
 * @returns 복호화된 데이터 또는 null
 */
export async function loadEncryptedReport<T = unknown>(id: string): Promise<T | null> {
  const kv = await getSecureKV();
  const raw = kv.getString(`report:${id}`);
  
  if (!raw) {
    return null;
  }
  
  const obj = JSON.parse(raw) as { v: number; iv: string; ct: string };
  if (obj.v !== 1) {
    throw new Error('Unsupported version');
  }
  
  const kek = await getOrCreateKey();
  const key = await importKey(b64uToBytes(kek));
  const iv = b64uToBytes(obj.iv);
  const ct = b64uToBytes(obj.ct);
  
  const pt = await subtle().decrypt({ name: 'AES-GCM', iv: iv as unknown as BufferSource }, key, ct as unknown as BufferSource);
  return JSON.parse(new TextDecoder().decode(new Uint8Array(pt))) as T;
}

/**
 * 암호화된 보고서 삭제
 * 
 * @param id - 보고서 ID
 */
export async function deleteEncryptedReport(id: string): Promise<void> {
  const kv = await getSecureKV();
  kv.delete(`report:${id}`);
}

/**
 * 모든 암호화된 보고서 삭제
 */
export async function wipeAllEncryptedReports(): Promise<void> {
  const kv = await getSecureKV();
  kv.getAllKeys().forEach((k: string) => {
    if (k.startsWith('report:')) {
      kv.delete(k);
    }
  });
}

/**
 * 키 회전: 새 키 생성 → 모든 레코드 재암호화(비동기 배치)
 */
export async function rotateLocalKey(): Promise<void> {
  await ensureModules();
  if (!SecureStore || !Random) {
    throw new Error('Required modules not available in this environment');
  }
  
  const oldKey = await getOrCreateKey();
  const kv = await getSecureKV();
  const keys = kv.getAllKeys().filter(k => k.startsWith('report:'));
  
  const oldCryptoKey = await importKey(b64uToBytes(oldKey));
  const newKeyBytes = await Random.getRandomBytesAsync(32);
  const newKeyB64u = Buffer.from(newKeyBytes).toString('base64url');
  
  await SecureStore.setItemAsync('appcore.kek.v1', newKeyB64u, {
    keychainAccessible: SecureStore.AFTER_FIRST_UNLOCK_THIS_DEVICE_ONLY,
  });
  
  const newCryptoKey = await importKey(new Uint8Array(newKeyBytes));
  
  for (const k of keys) {
    const raw = kv.getString(k)!;
    const obj = JSON.parse(raw) as { v: number; iv: string; ct: string };
    const ivOld = b64uToBytes(obj.iv);
    const ctOld = b64uToBytes(obj.ct);
    
    const pt = await subtle().decrypt({ name: 'AES-GCM', iv: ivOld as unknown as BufferSource }, oldCryptoKey, ctOld as unknown as BufferSource);
    const newIv = await Random.getRandomBytesAsync(12);
    const ctNew = new Uint8Array(await subtle().encrypt({ name: 'AES-GCM', iv: newIv as unknown as BufferSource }, newCryptoKey, pt));
    
    kv.set(k, JSON.stringify({ v: 1, iv: bytesToB64u(newIv), ct: bytesToB64u(ctNew) }));
  }
}
