set -euo pipefail
cd ~/tristan050-ai_ondevice_APP 2>/dev/null || true

cat > webcore_appcore_starter_4_17/backend/model_registry/tests/model_registry.test.ts <<'TS'
/**
 * Model Registry Tests
 * Verify signed artifact delivery and fail-closed behavior
 *
 * Contract:
 * - tests MUST NOT contain "OK=1" (evidence keys are emitted only by verify scripts on PASS)
 * - rely on Jest runner only (no custom runner / require.main side effects)
 */

import * as crypto from 'crypto';

import {
  createModel,
  createModelVersion,
  createArtifact,
  releaseModelVersion,
  setReleasePointer,
  getDelivery,
  initializeSigningKey,
} from '../services/storage';

import { verifyArtifact } from '../services/signing';

describe('Model Registry - Signed delivery + fail-closed', () => {
  beforeEach(() => {
    // If storage layer has global state reset helpers, call them here.
    // Intentionally left blank to avoid coupling; individual tests create isolated entities.
  });

  it('uploads, signs, verifies, releases, and delivers a model artifact', () => {
    // 1) signing key
    const signingKey = initializeSigningKey();
    expect(signingKey).toBeTruthy();
    expect(signingKey.key_id).toBe('v1-default');

    // 2) model + version
    const model = createModel('tenant1', 'user1', {
      name: 'test-model',
      description: 'Test model',
    });
    expect(model.id).toBeTruthy();
    expect(model.status).toBe('draft');

    const version = createModelVersion(model.id, 'tenant1', 'user1', { version: '1.0.0' });
    expect(version.id).toBeTruthy();
    expect(version.status).toBe('draft');

    // 3) artifact (storage layer is expected to attach signature + key_id)
    const fileData = Buffer.from('test model data');
    const sha256 = crypto.createHash('sha256').update(fileData).digest('hex');

    const artifact = createArtifact(version.id, 'tenant1', 'user1', {
      platform: 'android',
      runtime: 'onnx',
      file_path: '/tmp/test.onnx',
      file_size: fileData.length,
      sha256,
      model_id: model.id,
      version: version.version,
    });

    expect(artifact.id).toBeTruthy();
    expect(artifact.signature).toBeTruthy();
    expect(artifact.key_id).toBe('v1-default');

    // 4) verify signature (must be true)
    const isValid = verifyArtifact(
      artifact.sha256,
      model.id,
      version.version,
      artifact.platform,
      artifact.runtime,
      artifact.signature,
      signingKey.public_key
    );
    expect(isValid).toBe(true);

    // 5) release + pointer
    const released = releaseModelVersion(version.id, 'tenant1', 'user1');
    expect(released.status).toBe('released');

    const pointer = setReleasePointer(model.id, 'tenant1', 'user1', {
      platform: 'android',
      runtime: 'onnx',
      model_version_id: version.id,
      artifact_id: artifact.id,
    });
    expect(pointer.id).toBeTruthy();

    // 6) delivery view must include signature + key_id
    const delivery = getDelivery(model.id, 'tenant1', 'android', 'onnx');
    expect(delivery).toBeTruthy();
    expect(delivery?.artifact.id).toBe(artifact.id);
    expect(delivery?.artifact.signature).toBeTruthy();
    expect(delivery?.artifact.key_id).toBe('v1-default');
    expect(delivery?.version.version).toBe('1.0.0');
    expect(delivery?.signingKey.key_id).toBe('v1-default');
  });

  it('fails closed when signature is tampered', () => {
    const signingKey = initializeSigningKey();
    const model = createModel('tenant1', 'user1', { name: 'test-model' });
    const version = createModelVersion(model.id, 'tenant1', 'user1', { version: '1.0.0' });

    const fileData = Buffer.from('test model data');
    const sha256 = crypto.createHash('sha256').update(fileData).digest('hex');

    const artifact = createArtifact(version.id, 'tenant1', 'user1', {
      platform: 'android',
      runtime: 'onnx',
      file_path: '/tmp/test.onnx',
      file_size: fileData.length,
      sha256,
      model_id: model.id,
      version: version.version,
    });

    expect(artifact.signature).toBeTruthy();

    const sig = String(artifact.signature);
    const tamperedSignature = sig.slice(0, -1) + (sig.slice(-1) === 'X' ? 'Y' : 'X');

    const isValid = verifyArtifact(
      artifact.sha256,
      model.id,
      version.version,
      artifact.platform,
      artifact.runtime,
      tamperedSignature,
      signingKey.public_key
    );
    expect(isValid).toBe(false);
  });

  it('prevents overwriting a released version (idempotent / state-locked)', () => {
    const model = createModel('tenant1', 'user1', { name: 'test-model' });
    const version = createModelVersion(model.id, 'tenant1', 'user1', { version: '1.0.0' });

    // release once
    const released = releaseModelVersion(version.id, 'tenant1', 'user1');
    expect(released.status).toBe('released');

    // release again must throw
    expect(() => releaseModelVersion(version.id, 'tenant1', 'user1')).toThrow(/already released/i);
  });

  it('ensures delivery always includes signature + key id after release pointer is set', () => {
    const signingKey = initializeSigningKey();
    expect(signingKey.key_id).toBe('v1-default');

    const model = createModel('tenant1', 'user1', { name: 'test-model' });
    const version = createModelVersion(model.id, 'tenant1', 'user1', { version: '1.0.0' });

    const fileData = Buffer.from('test model data');
    const sha256 = crypto.createHash('sha256').update(fileData).digest('hex');

    const artifact = createArtifact(version.id, 'tenant1', 'user1', {
      platform: 'android',
      runtime: 'onnx',
      file_path: '/tmp/test.onnx',
      file_size: fileData.length,
      sha256,
      model_id: model.id,
      version: version.version,
    });

    const released = releaseModelVersion(version.id, 'tenant1', 'user1');
    expect(released.status).toBe('released');

    setReleasePointer(model.id, 'tenant1', 'user1', {
      platform: 'android',
      runtime: 'onnx',
      model_version_id: version.id,
      artifact_id: artifact.id,
    });

    const delivery = getDelivery(model.id, 'tenant1', 'android', 'onnx');
    expect(delivery).toBeTruthy();
    expect(delivery?.artifact.signature).toBeTruthy();
    expect(delivery?.artifact.key_id).toBe('v1-default');
  });
});
TS

# 1) 오염 재발 0 보장: tests 폴더에 OK=1 문자열이 없어야 정상
rg -n "OK=1" webcore_appcore_starter_4_17/backend/model_registry/tests || true
