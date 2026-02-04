/**
 * Collector 인증/테넌트 가드 미들웨어
 * API_KEYS 환경변수로 X-Tenant ↔ API Key 매핑 검증
 * 
 * @module auth
 */

import { Request, Response, NextFunction } from 'express';

// API_KEYS 환경변수 파싱: "default:collector-key,teamA:teamA-key"
function parseApiKeys(): Map<string, string> {
  const apiKeysStr = process.env.API_KEYS || 'default:collector-key';
  const map = new Map<string, string>();
  
  for (const pair of apiKeysStr.split(',')) {
    const [tenant, key] = pair.split(':').map(s => s.trim());
    if (tenant && key) {
      map.set(tenant, key);
    }
  }
  
  return map;
}

// API 키 맵 (캐시)
let apiKeyMap: Map<string, string> | null = null;

function getApiKeyMap(): Map<string, string> {
  if (!apiKeyMap) {
    apiKeyMap = parseApiKeys();
  }
  return apiKeyMap;
}

/**
 * 테넌트/API Key 검증 미들웨어
 * X-Tenant와 X-Api-Key 헤더를 검증하여 테넌트 격리 보장
 */
export function requireTenantAuth(
  req: Request,
  res: Response,
  next: NextFunction
): void {
  const tenantId = req.headers['x-tenant'] as string;
  const apiKey = req.headers['x-api-key'] as string;

  if (!tenantId) {
    res.status(401).json({ error: 'X-Tenant header required' });
    return;
  }

  if (!apiKey) {
    res.status(401).json({ error: 'X-Api-Key header required' });
    return;
  }

  // API 키 맵에서 테넌트에 해당하는 키 확인
  const keyMap = getApiKeyMap();
  const expectedKey = keyMap.get(tenantId);

  if (!expectedKey) {
    res.status(403).json({ error: `Tenant "${tenantId}" not found` });
    return;
  }

  if (apiKey !== expectedKey) {
    res.status(403).json({ error: 'Invalid API key for tenant' });
    return;
  }

  // 검증 통과 - req에 테넌트 정보 추가
  req.tenantId = tenantId;
  next();
}

/**
 * 서명 토큰 검증 (bundle.zip 다운로드용)
 * 토큰 내 tenant/id와 요청 파라미터 교차검증
 */
export function verifySignToken(
  req: Request,
  res: Response,
  next: NextFunction
): void {
  const token = req.query.token as string;
  const reportId = req.params.id;
  const tenantId = req.headers['x-tenant'] as string;

  if (!token) {
    res.status(401).json({ error: 'Token required' });
    return;
  }

  if (!tenantId) {
    res.status(401).json({ error: 'X-Tenant header required' });
    return;
  }

  // 토큰 검증 (페이로드 디코딩 및 교차검증)
  const signSecret = process.env.EXPORT_SIGN_SECRET || 'dev-secret';
  
  try {
    const crypto = require('node:crypto');
    
    // 토큰 형식: base64(payload).signature
    const [payloadBase64, signature] = token.split('.');
    
    if (!payloadBase64 || !signature) {
      res.status(403).json({ error: 'Invalid token format' });
      return;
    }
    
    // 서명 검증
    const expectedSignature = crypto
      .createHmac('sha256', signSecret)
      .update(payloadBase64)
      .digest('hex');
    
    if (signature !== expectedSignature) {
      res.status(403).json({ error: 'Invalid token signature' });
      return;
    }
    
    // 페이로드 디코딩
    const payloadStr = Buffer.from(payloadBase64, 'base64').toString('utf-8');
    const payload = JSON.parse(payloadStr);
    
    // expiresAt 검증
    if (payload.expiresAt < Date.now()) {
      res.status(403).json({ error: 'Token expired' });
      return;
    }
    
    // 토큰 페이로드의 tenantId와 reportId를 요청 파라미터와 교차검증
    if (payload.tenantId !== tenantId) {
      res.status(403).json({ error: 'Tenant ID mismatch' });
      return;
    }
    
    if (payload.reportId !== reportId) {
      res.status(403).json({ error: 'Report ID mismatch' });
      return;
    }
    
    // 검증 통과
    req.tenantId = payload.tenantId;
    req.reportId = payload.reportId;
    next();
  } catch (error) {
    console.error('Token verification error:', error);
    res.status(500).json({ error: 'Token verification failed' });
  }
}

