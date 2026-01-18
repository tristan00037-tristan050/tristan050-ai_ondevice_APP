/**
 * OIDC Token Verification
 * Generic IdP support (Okta/AzureAD/Keycloak compatible)
 */

import jwt from 'jsonwebtoken';
import jwksClient from 'jwks-rsa';
import { Request } from 'express';

export interface OIDCConfig {
  issuer: string;
  audience: string;
  jwksUri: string;
}

export interface TokenPayload {
  sub: string; // Subject (user identifier)
  iss: string; // Issuer
  aud: string | string[]; // Audience
  exp: number; // Expiration
  iat?: number; // Issued at
  tenant_id?: string;
  email?: string;
  name?: string;
  roles?: string[];
  [key: string]: unknown;
}

export interface AuthContext {
  user_id: string;
  tenant_id: string;
  email?: string;
  name?: string;
  roles?: string[];
}

// JWKS client cache (per issuer)
const jwksClients = new Map<string, jwksClient.JwksClient>();

function getJwksClient(jwksUri: string): jwksClient.JwksClient {
  if (!jwksClients.has(jwksUri)) {
    const client = jwksClient({
      jwksUri,
      cache: true,
      cacheMaxAge: 86400000, // 24 hours
    });
    jwksClients.set(jwksUri, client);
  }
  return jwksClients.get(jwksUri)!;
}

function getKey(header: jwt.JwtHeader, jwksUri: string): Promise<string> {
  return new Promise((resolve, reject) => {
    const client = getJwksClient(jwksUri);
    client.getSigningKey(header.kid, (err, key) => {
      if (err) {
        return reject(err);
      }
      const signingKey = key.getPublicKey();
      resolve(signingKey);
    });
  });
}

/**
 * Verify OIDC token
 * Fail-Closed: invalid token => throw error
 */
export async function verifyOIDCToken(
  token: string,
  config: OIDCConfig
): Promise<TokenPayload> {
  // Decode header to get kid
  const decoded = jwt.decode(token, { complete: true });
  if (!decoded || typeof decoded === 'string' || !decoded.header) {
    throw new Error('Invalid token format');
  }

  // Get signing key from JWKS
  const signingKey = await getKey(decoded.header, config.jwksUri);

  // Verify token
  const payload = jwt.verify(token, signingKey, {
    issuer: config.issuer,
    audience: config.audience,
    algorithms: ['RS256'],
  }) as TokenPayload;

  // Fail-Closed: Validate required claims
  if (!payload.sub) {
    throw new Error('Missing sub claim');
  }
  if (!payload.iss || payload.iss !== config.issuer) {
    throw new Error('Invalid issuer');
  }
  if (!payload.aud || (Array.isArray(payload.aud) ? !payload.aud.includes(config.audience) : payload.aud !== config.audience)) {
    throw new Error('Invalid audience');
  }
  if (!payload.exp || payload.exp < Date.now() / 1000) {
    throw new Error('Token expired');
  }

  return payload;
}

/**
 * Extract auth context from request
 * Fail-Closed: no token or invalid => throw error
 */
export async function extractAuthContext(
  req: Request,
  config: OIDCConfig
): Promise<AuthContext> {
  const authHeader = req.headers.authorization;
  if (!authHeader || !authHeader.startsWith('Bearer ')) {
    throw new Error('Missing or invalid Authorization header');
  }

  const token = authHeader.substring(7);
  const payload = await verifyOIDCToken(token, config);

  // Fail-Closed: tenant_id required
  if (!payload.tenant_id) {
    throw new Error('Missing tenant_id in token');
  }

  return {
    user_id: payload.sub,
    tenant_id: payload.tenant_id,
    email: payload.email,
    name: payload.name,
    roles: payload.roles,
  };
}

