'use strict';

import type { RuntimeManifestV1 } from './runtime_manifest_builder_v1';

function assertSha256Maybe(value: unknown, field: string): void {
  if (value === undefined || value === null) return;
  if (typeof value !== 'string' || !/^[0-9a-f]{64}$/.test(value)) {
    throw new Error(`RUNTIME_MANIFEST_INVALID_SHA256:${field}`);
  }
}

export function assertRuntimeManifestV1(obj: unknown): asserts obj is RuntimeManifestV1 {
  if (!obj || typeof obj !== 'object') {
    throw new Error('RUNTIME_MANIFEST_NOT_OBJECT');
  }
  const o = obj as Record<string, unknown>;

  if (o['schema_version'] !== 1) {
    throw new Error(`RUNTIME_MANIFEST_SCHEMA_VERSION_INVALID:${o['schema_version']}`);
  }
  if (o['logical_pack_id'] !== 'micro_default' && o['logical_pack_id'] !== 'small_default') {
    throw new Error(`RUNTIME_MANIFEST_LOGICAL_PACK_ID_INVALID:${o['logical_pack_id']}`);
  }
  if (o['model_format'] !== 'onnx') {
    throw new Error(`RUNTIME_MANIFEST_MODEL_FORMAT_INVALID:${o['model_format']}`);
  }
  if (o['quantization_mode'] !== 'weight_only_int4') {
    throw new Error(`RUNTIME_MANIFEST_QUANTIZATION_MODE_INVALID:${o['quantization_mode']}`);
  }
  if (typeof o['context_length'] !== 'number' || o['context_length'] <= 0) {
    throw new Error(`RUNTIME_MANIFEST_CONTEXT_LENGTH_INVALID:${o['context_length']}`);
  }

  if (!obj || typeof obj !== 'object') {
    throw new Error('RUNTIME_MANIFEST_ARTIFACTS_INVALID');
  }

  if (!o['artifacts'] || typeof o['artifacts'] !== 'object') {
    throw new Error('RUNTIME_MANIFEST_ARTIFACTS_INVALID');
  }
  const art = o['artifacts'] as Record<string, unknown>;

  // required digest 3개 — 누락 시 필드명 명시
  if (!art['weights_digest_sha256'] || typeof art['weights_digest_sha256'] !== 'string') {
    throw new Error('RUNTIME_MANIFEST_REQUIRED_DIGEST_MISSING:weights_digest_sha256');
  }
  if (!art['tokenizer_digest_sha256'] || typeof art['tokenizer_digest_sha256'] !== 'string') {
    throw new Error('RUNTIME_MANIFEST_REQUIRED_DIGEST_MISSING:tokenizer_digest_sha256');
  }
  if (!art['chat_template_digest_sha256'] || typeof art['chat_template_digest_sha256'] !== 'string') {
    throw new Error('RUNTIME_MANIFEST_REQUIRED_DIGEST_MISSING:chat_template_digest_sha256');
  }

  // SHA-256 형식 검증
  assertSha256Maybe(art['weights_digest_sha256'], 'weights_digest_sha256');
  assertSha256Maybe(art['tokenizer_digest_sha256'], 'tokenizer_digest_sha256');
  assertSha256Maybe(art['chat_template_digest_sha256'], 'chat_template_digest_sha256');

  if (art['config_digest_sha256'] !== undefined) {
    assertSha256Maybe(String(art['config_digest_sha256']), 'config_digest_sha256');
  }
}
