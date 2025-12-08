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

// 웹 환경 체크: window가 있고 navigator.product가 'ReactNative'가 아니면 웹
const isWeb = typeof window !== 'undefined' && 
  (typeof navigator === 'undefined' || (navigator as any).product !== 'ReactNative');

// Base64url 인코딩/디코딩 유틸 (웹 환경용)
function bytesToBase64url(bytes: Uint8Array): string {
  if (isWeb) {
    // 웹 환경: Uint8Array를 문자열로 변환 후 btoa 사용
    let binary = '';
    for (let i = 0; i < bytes.length; i++) {
      binary += String.fromCharCode(bytes[i]);
    }
    // base64를 base64url로 변환 (+ -> -, / -> _, = 제거)
    return btoa(binary)
      .replace(/\+/g, '-')
      .replace(/\//g, '_')
      .replace(/=/g, '');
  } else {
    // Node.js/RN 환경: Buffer 사용
    return Buffer.from(bytes).toString('base64url');
  }
}

function base64urlToBytes(s: string): Uint8Array {
  if (isWeb) {
    // base64url를 base64로 변환
    let base64 = s.replace(/-/g, '+').replace(/_/g, '/');
    // padding 추가
    while (base64.length % 4) {
      base64 += '=';
    }
    const binary = atob(base64);
    const bytes = new Uint8Array(binary.length);
    for (let i = 0; i < binary.length; i++) {
      bytes[i] = binary.charCodeAt(i);
    }
    return bytes;
  } else {
    // Node.js/RN 환경: Buffer 사용
    return new Uint8Array(Buffer.from(s, 'base64url'));
  }
}

// 런타임에서 동적으로 로드 (React Native 환경)
// Node.js 빌드 환경에서는 타입 체크만 수행
let SecureStore: SecureStoreType | null = null;
let MMKV: MMKVType['MMKV'] | null = null;
let Random: RandomType | null = null;

async function ensureModules(): Promise<void> {
  // 웹 환경에서는 expo 모듈을 사용하지 않음
  if (isWeb) {
    return;
  }
  
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
  const keyId = 'appcore.kek.v1';
  
  // 웹 환경: localStorage 사용
  if (isWeb) {
    let key = localStorage.getItem(keyId);
    if (!key) {
      // 웹에서 랜덤 키 생성 (crypto.getRandomValues 사용)
      const bytes = new Uint8Array(32);
      crypto.getRandomValues(bytes);
      key = bytesToBase64url(bytes);
      localStorage.setItem(keyId, key);
    }
    return key;
  }
  
  // React Native 환경: SecureStore 사용
  await ensureModules();
  if (!SecureStore) {
    throw new Error('SecureStore not available in this environment');
  }
  
  let key: string | null = await SecureStore.getItemAsync(keyId);
  
  if (!key) {
    if (!Random) {
      throw new Error('Random not available in this environment');
    }
    const bytes = await Random.getRandomBytesAsync(32);
    // Base64url
    key = bytesToBase64url(bytes);
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

// 웹 환경용 localStorage 래퍼
class WebStorageKV {
  private prefix: string;
  
  constructor(prefix: string) {
    this.prefix = prefix;
  }
  
  getString(key: string): string | undefined {
    const value = localStorage.getItem(`${this.prefix}:${key}`);
    return value ?? undefined;
  }
  
  set(key: string, value: string): void {
    localStorage.setItem(`${this.prefix}:${key}`, value);
  }
  
  delete(key: string): void {
    localStorage.removeItem(`${this.prefix}:${key}`);
  }
  
  getAllKeys(): string[] {
    const keys: string[] = [];
    for (let i = 0; i < localStorage.length; i++) {
      const fullKey = localStorage.key(i);
      if (fullKey?.startsWith(`${this.prefix}:`)) {
        keys.push(fullKey.substring(this.prefix.length + 1));
      }
    }
    return keys;
  }
}

export async function getSecureKV(): Promise<any> {
  // 웹 환경: localStorage 기반 KV 사용
  if (isWeb) {
    if (!_mmkv) {
      _mmkv = new WebStorageKV('appcore.secure');
    }
    return _mmkv;
  }
  
  // React Native 환경: MMKV 사용
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
  return base64urlToBytes(s);
}

function bytesToB64u(b: Bytes): string {
  return bytesToBase64url(b);
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
  
  // 웹 환경: crypto.getRandomValues 사용
  let iv: Uint8Array;
  if (isWeb) {
    iv = new Uint8Array(12);
    crypto.getRandomValues(iv);
  } else {
    if (!Random) {
      throw new Error('Random not available in this environment');
    }
    iv = await Random.getRandomBytesAsync(12);
  }
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
  const keys = kv.getAllKeys().filter((k: string) => k.startsWith('report:'));
  
  const oldCryptoKey = await importKey(b64uToBytes(oldKey));
  
  // 웹 환경: crypto.getRandomValues 사용
  let newKeyBytes: Uint8Array;
  if (isWeb) {
    newKeyBytes = new Uint8Array(32);
    crypto.getRandomValues(newKeyBytes);
  } else {
    if (!Random) {
      throw new Error('Random not available in this environment');
    }
    newKeyBytes = await Random.getRandomBytesAsync(32);
  }
  const newKeyB64u = bytesToBase64url(newKeyBytes);
  
  if (isWeb) {
    localStorage.setItem('appcore.kek.v1', newKeyB64u);
  } else {
    if (!SecureStore) {
      throw new Error('SecureStore not available');
    }
    await SecureStore.setItemAsync('appcore.kek.v1', newKeyB64u, {
      keychainAccessible: SecureStore.AFTER_FIRST_UNLOCK_THIS_DEVICE_ONLY,
    });
  }
  
  const newCryptoKey = await importKey(new Uint8Array(newKeyBytes));
  
  for (const k of keys) {
    const raw = kv.getString(k)!;
    const obj = JSON.parse(raw) as { v: number; iv: string; ct: string };
    const ivOld = b64uToBytes(obj.iv);
    const ctOld = b64uToBytes(obj.ct);
    
    const pt = await subtle().decrypt({ name: 'AES-GCM', iv: ivOld as unknown as BufferSource }, oldCryptoKey, ctOld as unknown as BufferSource);
    
    // 웹 환경: crypto.getRandomValues 사용
    let newIv: Uint8Array;
    if (isWeb) {
      newIv = new Uint8Array(12);
      crypto.getRandomValues(newIv);
    } else {
      if (!Random) {
        throw new Error('Random not available');
      }
      newIv = await Random.getRandomBytesAsync(12);
    }
    const ctNew = new Uint8Array(await subtle().encrypt({ name: 'AES-GCM', iv: newIv as unknown as BufferSource }, newCryptoKey, pt));
    
    kv.set(k, JSON.stringify({ v: 1, iv: bytesToB64u(newIv), ct: bytesToB64u(ctNew) }));
  }
}
