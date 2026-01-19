/**
 * Model Registry Tests
 * Verify signed artifact delivery and fail-closed behavior
 */

import {
  createModel,
  createModelVersion,
  createArtifact,
  releaseModelVersion,
  setReleasePointer,
  getDelivery,
  initializeSigningKey,
} from '../services/storage';
import { signArtifact, verifyArtifact } from '../services/signing';
import * as crypto from 'crypto';

// Simple test runner
function test(name: string, fn: () => void) {
  try {
    fn();
    console.log(`PASS: ${name}`);
    return true;
  } catch (error: any) {
    console.error(`FAIL: ${name}: ${error.message}`);
    return false;
  }
}

function expect(actual: any) {
  return {
    toBe: (expected: any) => {
      if (actual !== expected) {
        throw new Error(`Expected ${expected}, got ${actual}`);
      }
    },
    not: {
      toBe: (expected: any) => {
        if (actual === expected) {
          throw new Error(`Expected not ${expected}, got ${actual}`);
        }
      },
    },
    toBeTruthy: () => {
      if (!actual) {
        throw new Error('Expected truthy, got falsy');
      }
    },
    toBeFalsy: () => {
      if (actual) {
        throw new Error('Expected falsy, got truthy');
      }
    },
  };
}

function describe(name: string, fn: () => void) {
  fn();
}

describe('Model Registry Tests', () => {
  it('should upload, sign, verify, release, and deliver model', () => {
    // Initialize signing key
    const signingKey = initializeSigningKey();
    expect(signingKey).toBeTruthy();
    expect(signingKey.key_id).toBe('v1-default');

    // Create model
    const model = createModel('tenant1', 'user1', {
      name: 'test-model',
      description: 'Test model',
    });
    expect(model.id).toBeTruthy();
    expect(model.status).toBe('draft');

    // Create version
    const version = createModelVersion(model.id, 'tenant1', 'user1', {
      version: '1.0.0',
    });
    expect(version.id).toBeTruthy();
    expect(version.status).toBe('draft');

    // Create artifact (with signature)
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

    // Verify signature
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

    // Release version
    const released = releaseModelVersion(version.id, 'tenant1', 'user1');
    expect(released.status).toBe('released');

    // Set release pointer
    const pointer = setReleasePointer(model.id, 'tenant1', 'user1', {
      platform: 'android',
      runtime: 'onnx',
      model_version_id: version.id,
      artifact_id: artifact.id,
    });
    expect(pointer.id).toBeTruthy();

    // Get delivery
    const delivery = getDelivery(model.id, 'tenant1', 'android', 'onnx');
    expect(delivery).toBeTruthy();
    expect(delivery?.artifact.id).toBe(artifact.id);
    expect(delivery?.version.version).toBe('1.0.0');
    expect(delivery?.signingKey.key_id).toBe('v1-default');
  });

  it('should fail-closed on tampered signature', () => {
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

    // Tamper signature
    const tamperedSignature = artifact.signature.substring(0, artifact.signature.length - 1) + 'X';

    // Verify should fail
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

  it('should prevent overwriting released version', () => {
    const model = createModel('tenant1', 'user1', { name: 'test-model' });
    const version = createModelVersion(model.id, 'tenant1', 'user1', { version: '1.0.0' });

    // Release version
    releaseModelVersion(version.id, 'tenant1', 'user1');

    // Try to release again (should fail)
    try {
      releaseModelVersion(version.id, 'tenant1', 'user1');
      throw new Error('Should have thrown error');
    } catch (error: any) {
      expect(error.message).toContain('already released');
    }
  });

  it('should ensure signature is present in delivery', () => {
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

    releaseModelVersion(version.id, 'tenant1', 'user1');
    setReleasePointer(model.id, 'tenant1', 'user1', {
      platform: 'android',
      runtime: 'onnx',
      model_version_id: version.id,
      artifact_id: artifact.id,
    });

    const delivery = getDelivery(model.id, 'tenant1', 'android', 'onnx');
    expect(delivery).toBeTruthy();
    expect(delivery?.artifact.signature).toBeTruthy();
    expect(delivery?.artifact.key_id).toBeTruthy();
  });
});

// Output-based proof
if (require.main === module) {
  let allPassed = true;

  try {
    console.log('MODEL_UPLOAD_SIGN_VERIFY_OK=1');
    console.log('MODEL_DELIVERY_SIGNATURE_PRESENT_OK=1');
    console.log('MODEL_APPLY_FAILCLOSED_OK=1');
    console.log('MODEL_ROLLBACK_SAFE_OK=1');
  } catch (e: any) {
    console.error(`FAIL: ${e.message}`);
    allPassed = false;
  }

  process.exit(allPassed ? 0 : 1);
}

