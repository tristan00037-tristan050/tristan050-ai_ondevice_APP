/**
 * Signing Service
 * Ed25519 signature generation and verification
 * Rotate-ready key management
 */

import * as crypto from 'crypto';

export interface SigningKey {
  key_id: string;
  public_key: string; // Base64 encoded
  private_key: string; // Base64 encoded (server-managed)
  created_at: Date;
  active: boolean;
}

/**
 * Generate Ed25519 key pair
 */
export function generateKeyPair(): { publicKey: string; privateKey: string } {
  const { publicKey, privateKey } = crypto.generateKeyPairSync('ed25519');
  return {
    publicKey: publicKey.export({ type: 'spki', format: 'pem' }).toString('base64'),
    privateKey: privateKey.export({ type: 'pkcs8', format: 'pem' }).toString('base64'),
  };
}

/**
 * Sign data with Ed25519 private key
 */
export function sign(data: Buffer, privateKeyBase64: string): string {
  const privateKey = crypto.createPrivateKey({
    key: Buffer.from(privateKeyBase64, 'base64'),
    format: 'pem',
    type: 'pkcs8',
  });
  
  const signature = crypto.sign(null, data, privateKey);
  return signature.toString('base64');
}

/**
 * Verify signature with Ed25519 public key
 */
export function verify(data: Buffer, signatureBase64: string, publicKeyBase64: string): boolean {
  try {
    const publicKey = crypto.createPublicKey({
      key: Buffer.from(publicKeyBase64, 'base64'),
      format: 'pem',
      type: 'spki',
    });
    
    const signature = Buffer.from(signatureBase64, 'base64');
    return crypto.verify(null, data, publicKey, signature);
  } catch (error) {
    return false;
  }
}

/**
 * Sign artifact (hash + metadata)
 */
export function signArtifact(
  sha256: string,
  modelId: string,
  version: string,
  platform: string,
  runtime: string,
  privateKeyBase64: string
): string {
  // Sign: sha256 + model_id + version + platform + runtime
  const dataToSign = `${sha256}:${modelId}:${version}:${platform}:${runtime}`;
  return sign(Buffer.from(dataToSign, 'utf-8'), privateKeyBase64);
}

/**
 * Verify artifact signature
 */
export function verifyArtifact(
  sha256: string,
  modelId: string,
  version: string,
  platform: string,
  runtime: string,
  signatureBase64: string,
  publicKeyBase64: string
): boolean {
  const dataToSign = `${sha256}:${modelId}:${version}:${platform}:${runtime}`;
  return verify(Buffer.from(dataToSign, 'utf-8'), signatureBase64, publicKeyBase64);
}

