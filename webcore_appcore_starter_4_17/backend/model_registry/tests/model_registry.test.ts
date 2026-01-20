set -euo pipefail
cd ~/tristan050-ai_ondevice_APP

git fetch -q origin
git checkout main
git pull -q --ff-only

# 새 브랜치
BR="fix/svr03-remove-ok-contamination-20260120"
git checkout -b "$BR"

# 파일 통째로 교체 (tests 안에 OK=1 / require.main 블록이 절대 없도록)
cat > webcore_appcore_starter_4_17/backend/model_registry/tests/model_registry.test.ts <<'TS'
/**
 * Model Registry Tests
 * Verify signed artifact delivery and fail-closed behavior
 *
 * Hard rule:
 * - tests MUST NOT contain "OK=1" (evidence keys are emitted only by verify scripts on PASS)
 * - no require.main side effects in tests
 * - Jest-only (describe/it/expect), no custom runner
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

describe('Model Registry - signed delivery + fail-closed', () => {
  it('uploads, signs, verifies, releases, and delivers a model artifact', () => {
    const signingKey = initializeSigningKey();
    expect(signingKey).toBeTruthy();
    expect(signingKey.key_id).toBe('v1-default');

    const model = createModel('tenant1', 'user1', {
      name: 'test-model',
      description: 'Test model',
    });
    expect(model.id).toBeTruthy();
    expect(model.status).toBe('draft');

    const version = createModelVersion(model.id, 'tenant1', 'user1', { version: '1.0.0' });
    expect(version.id).toBeTruthy();
    expect(version.status).toBe('draft');

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

    const released = releaseModelVersion(version.id, 'tenant1', 'user1');
    expect(released.status).toBe('released');

    const pointer = setReleasePointer(model.id, 'tenant1', 'user1', {
      platform: 'android',
      runtime: 'onnx',
      model_version_id: version.id,
      artifact_id: artifact.id,
    });
    expect(pointer.id).toBeTruthy();

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

    const sig = String(artifact.signature);
    expect(sig.length).toBeGreaterThan(0);
    const tampered = sig.slice(0, -1) + (sig.slice(-1) === 'X' ? 'Y' : 'X');

    const isValid = verifyArtifact(
      artifact.sha256,
      model.id,
      version.version,
      artifact.platform,
      artifact.runtime,
      tampered,
      signingKey.public_key
    );
    expect(isValid).toBe(false);
  });

  it('prevents overwriting a released version', () => {
    const model = createModel('tenant1', 'user1', { name: 'test-model' });
    const version = createModelVersion(model.id, 'tenant1', 'user1', { version: '1.0.0' });

    const released = releaseModelVersion(version.id, 'tenant1', 'user1');
    expect(released.status).toBe('released');

    expect(() => releaseModelVersion(version.id, 'tenant1', 'user1')).toThrow(/already released/i);
  });

  it('ensures delivery includes signature + key id after release pointer is set', () => {
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
    expect(delivery?.artifact.key_id).toBe('v1-default');
  });
});
TS

echo "== 1) OK=1 contamination must be ZERO =="
rg -n "OK=1" webcore_appcore_starter_4_17/backend/model_registry/tests || true
