"use strict";
/**
 * OIDC Token Verification
 * Generic IdP support (Okta/AzureAD/Keycloak compatible)
 */
var __importDefault = (this && this.__importDefault) || function (mod) {
    return (mod && mod.__esModule) ? mod : { "default": mod };
};
Object.defineProperty(exports, "__esModule", { value: true });
exports.verifyOIDCToken = verifyOIDCToken;
exports.extractAuthContext = extractAuthContext;
const jsonwebtoken_1 = __importDefault(require("jsonwebtoken"));
const jwks_rsa_1 = __importDefault(require("jwks-rsa"));
// JWKS client cache (per issuer)
const jwksClients = new Map();
function getJwksClient(jwksUri) {
    if (!jwksClients.has(jwksUri)) {
        const client = (0, jwks_rsa_1.default)({
            jwksUri,
            cache: true,
            cacheMaxAge: 86400000, // 24 hours
        });
        jwksClients.set(jwksUri, client);
    }
    return jwksClients.get(jwksUri);
}
function getKey(header, jwksUri) {
    return new Promise((resolve, reject) => {
        const client = getJwksClient(jwksUri);
        client.getSigningKey(header.kid, (err, key) => {
            if (err) {
                return reject(err);
            }
            if (!key) {
                return reject(new Error("JWKS signing key not found"));
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
async function verifyOIDCToken(token, config) {
    // Decode header to get kid
    const decoded = jsonwebtoken_1.default.decode(token, { complete: true });
    if (!decoded || typeof decoded === 'string' || !decoded.header) {
        throw new Error('Invalid token format');
    }
    // Get signing key from JWKS
    const signingKey = await getKey(decoded.header, config.jwksUri);
    // Verify token
    const payload = jsonwebtoken_1.default.verify(token, signingKey, {
        issuer: config.issuer,
        audience: config.audience,
        algorithms: ['RS256'],
    });
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
async function extractAuthContext(req, config) {
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
