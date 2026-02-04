/**
 * 서명 토큰 캐시 데이터베이스 레포지토리
 * 멱등성 보장을 위한 토큰 캐시
 * 
 * @module db/signTokenCache
 */

import { query } from './client.js';

export interface SignTokenCache {
  cacheKey: string;
  token: string;
  expiresAt: number;
  createdAt: number;
}

/**
 * 토큰 캐시 조회
 */
export async function getTokenCache(
  cacheKey: string
): Promise<{ token: string; expiresAt: number } | null> {
  const result = await query<{
    token: string;
    expires_at: number;
  }>(
    `SELECT token, expires_at
     FROM sign_token_cache
     WHERE cache_key = $1 AND expires_at > $2`,
    [cacheKey, Date.now()]
  );

  if (result.rows.length === 0) {
    return null;
  }

  return {
    token: result.rows[0].token,
    expiresAt: result.rows[0].expires_at,
  };
}

/**
 * 토큰 캐시 저장
 */
export async function setTokenCache(cache: SignTokenCache): Promise<void> {
  await query(
    `INSERT INTO sign_token_cache (cache_key, token, expires_at, created_at)
     VALUES ($1, $2, $3, $4)
     ON CONFLICT (cache_key) DO UPDATE SET
       token = $2,
       expires_at = $3,
       created_at = $4`,
    [cache.cacheKey, cache.token, cache.expiresAt, cache.createdAt]
  );
}

/**
 * 만료된 토큰 정리
 */
export async function cleanupExpiredTokens(): Promise<number> {
  const result = await query(
    `DELETE FROM sign_token_cache WHERE expires_at < $1`,
    [Date.now()]
  );
  return result.rowCount || 0;
}


