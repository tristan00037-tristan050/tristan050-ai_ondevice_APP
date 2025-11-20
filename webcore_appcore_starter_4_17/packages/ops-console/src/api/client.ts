/**
 * Collector API 클라이언트
 * ETag/If-None-Match 지원, localStorage 캐시
 * 
 * @module client
 */

const COLLECTOR_URL = import.meta.env.VITE_COLLECTOR_URL || 'http://localhost:9090';
const API_KEY = import.meta.env.VITE_API_KEY || '';
const TENANT = import.meta.env.VITE_TENANT || 'default';

// localStorage 키
const CACHE_PREFIX = '@qc_cache_';
const ETAG_PREFIX = '@qc_etag_';

interface CacheEntry {
  data: unknown;
  etag: string;
  timestamp: number;
}

/**
 * ETag 캐시에서 항목 조회
 */
function getCached(key: string): CacheEntry | null {
  try {
    const etagKey = ETAG_PREFIX + key;
    const cacheKey = CACHE_PREFIX + key;
    
    const etag = localStorage.getItem(etagKey);
    const cached = localStorage.getItem(cacheKey);
    
    if (etag && cached) {
      const entry: CacheEntry = JSON.parse(cached);
      return { ...entry, etag };
    }
  } catch (error) {
    console.error('Cache read error:', error);
  }
  
  return null;
}

/**
 * ETag 캐시에 항목 저장
 */
function setCached(key: string, data: unknown, etag: string): void {
  try {
    const etagKey = ETAG_PREFIX + key;
    const cacheKey = CACHE_PREFIX + key;
    
    const entry: CacheEntry = {
      data,
      etag,
      timestamp: Date.now(),
    };
    
    localStorage.setItem(etagKey, etag);
    localStorage.setItem(cacheKey, JSON.stringify(entry));
  } catch (error) {
    console.error('Cache write error:', error);
  }
}

/**
 * API 요청 (ETag/If-None-Match 지원)
 */
async function fetchWithETag<T>(
  endpoint: string,
  options: RequestInit = {}
): Promise<{ data: T; fromCache: boolean }> {
  const url = `${COLLECTOR_URL}${endpoint}`;
  const cacheKey = endpoint;
  
  // 캐시에서 ETag 조회
  const cached = getCached(cacheKey);
  const headers: Record<string, string> = {
    'X-Api-Key': API_KEY,
    'X-Tenant': TENANT,
    'Content-Type': 'application/json',
    ...(options.headers as Record<string, string>),
  };
  
  // If-None-Match 헤더 추가
  if (cached?.etag) {
    headers['If-None-Match'] = cached.etag;
  }
  
  try {
    const response = await fetch(url, {
      ...options,
      headers,
    });
    
    // 304 Not Modified - 캐시 사용
    if (response.status === 304 && cached) {
      return {
        data: cached.data as T,
        fromCache: true,
      };
    }
    
    if (!response.ok) {
      throw new Error(`HTTP ${response.status}: ${await response.text()}`);
    }
    
    const data = await response.json();
    const etag = response.headers.get('ETag');
    
    // ETag가 있으면 캐시에 저장
    if (etag) {
      setCached(cacheKey, data, etag);
    }
    
    return {
      data,
      fromCache: false,
    };
  } catch (error) {
    // 네트워크 오류 시 캐시 사용 (있는 경우)
    if (cached && error instanceof TypeError) {
      console.warn('Network error, using cache:', error);
      return {
        data: cached.data as T,
        fromCache: true,
      };
    }
    
    throw error;
  }
}

/**
 * GET 요청
 */
export async function get<T>(endpoint: string): Promise<T> {
  const result = await fetchWithETag<T>(endpoint, {
    method: 'GET',
  });
  return result.data;
}

/**
 * POST 요청
 */
export async function post<T>(endpoint: string, body: unknown): Promise<T> {
  const result = await fetchWithETag<T>(endpoint, {
    method: 'POST',
    body: JSON.stringify(body),
  });
  return result.data;
}

/**
 * 캐시 무효화
 */
export function invalidateCache(endpoint: string): void {
  const cacheKey = endpoint;
  try {
    localStorage.removeItem(ETAG_PREFIX + cacheKey);
    localStorage.removeItem(CACHE_PREFIX + cacheKey);
  } catch (error) {
    console.error('Cache invalidation error:', error);
  }
}

/**
 * 모든 캐시 무효화
 */
export function clearAllCache(): void {
  try {
    const keys = Object.keys(localStorage);
    keys.forEach(key => {
      if (key.startsWith(CACHE_PREFIX) || key.startsWith(ETAG_PREFIX)) {
        localStorage.removeItem(key);
      }
    });
  } catch (error) {
    console.error('Cache clear error:', error);
  }
}

