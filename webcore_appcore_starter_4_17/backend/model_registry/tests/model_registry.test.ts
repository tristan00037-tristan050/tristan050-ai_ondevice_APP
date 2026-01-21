/**
 * Model Registry Tests
 * Verify signed artifact delivery and fail-closed behavior
 *
 * Hard rule:
 * - tests MUST NOT contain evidence string patterns (evidence keys are emitted only by verify scripts on PASS)
 * - no require.main side effects in tests
 * - Jest-only (describe/it/expect), no custom runner
 */

import { describe, it, expect, beforeEach } from '@jest/globals';
import { createModel, createModelVersion, createArtifact, clearAll } from '../storage/service';
import { verifyArtifact } from '../services/signing';
import * as crypto from 'crypto';

describe('Model Registry - Signed Artifact Delivery', () => {
  let signingKey: crypto.KeyPairKeyObjectResult;

  beforeEach(() => {
    clearAll();
    signingKey = crypto.generateKeyPairSync('ed25519');
  });

  function signArtifactData(
    sha256: string,
    modelId: string,
    version: string,
    platform: string,
    runtime: string
  ): string {
    const dataToSign = `${sha256}:${modelId}:${version}:${platform}:${runtime}`;
    const signature = crypto.sign(null, Buffer.from(dataToSign, 'utf-8'), signingKey.privateKey);
    return signature.toString('base64');
  }

  function getPublicKeyBase64(): string {
    const pem = signingKey.publicKey.export({ type: 'spki', format: 'pem' }) as string;
    return Buffer.from(pem, 'utf-8').toString('base64');
  }

  it('should deliver signed artifact with meta-only metadata', () => {
    const model = createModel('tenant1', { name: 'test-model' });
    expect(model.id).toBeTruthy();
    expect(model.status).toBe('active');

    const version = createModelVersion('tenant1', model.id, { version: '1.0.0' });
    expect(version).toBeTruthy();
    expect(version?.status).toBe('draft');

    const fileData = Buffer.from('test model data');
    const sha256 = crypto.createHash('sha256').update(fileData).digest('hex');

    const artifact = createArtifact('tenant1', model.id, version!.id, {
      platform: 'android',
      runtime: 'onnx',
      sha256,
      size_bytes: fileData.length,
      storage_ref: '/tmp/test.onnx',
    });
    expect(artifact).toBeTruthy();
    expect(artifact?.sha256).toBe(sha256);

    const signature = signArtifactData(
      artifact!.sha256,
      model.id,
      version!.version,
      artifact!.platform,
      artifact!.runtime
    );
    expect(signature).toBeTruthy();

    const isValid = verifyArtifact(
      artifact!.sha256,
      model.id,
      version!.version,
      artifact!.platform,
      artifact!.runtime,
      signature,
      getPublicKeyBase64()
    );
    expect(isValid).toBe(true);
  });

  it('should fail-closed on tampered signature', () => {
    const model = createModel('tenant1', { name: 'test-model' });
    const version = createModelVersion('tenant1', model.id, { version: '1.0.0' });

    const fileData = Buffer.from('test model data');
    const sha256 = crypto.createHash('sha256').update(fileData).digest('hex');

    const artifact = createArtifact('tenant1', model.id, version!.id, {
      platform: 'android',
      runtime: 'onnx',
      sha256,
      size_bytes: fileData.length,
      storage_ref: '/tmp/test.onnx',
    });

    const signature = signArtifactData(
      artifact!.sha256,
      model.id,
      version!.version,
      artifact!.platform,
      artifact!.runtime
    );

    const tamperedSignature = Buffer.from(signature, 'base64');
    tamperedSignature[0] = (tamperedSignature[0] + 1) % 256;
    const tamperedSignatureBase64 = tamperedSignature.toString('base64');

    const isValid = verifyArtifact(
      artifact!.sha256,
      model.id,
      version!.version,
      artifact!.platform,
      artifact!.runtime,
      tamperedSignatureBase64,
      getPublicKeyBase64()
    );
    expect(isValid).toBe(false);
  });
});
