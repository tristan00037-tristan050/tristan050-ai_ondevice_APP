'use strict';

import { isValidSha256Hex } from './exec_mode_result_v1';

export interface RuntimeManifestArtifactsV1 {
  weights_digest_sha256: string;
  tokenizer_digest_sha256: string;
  chat_template_digest_sha256: string;
  config_digest_sha256?: string;
}

export interface RuntimeManifestBuildInputV1 {
  logical_pack_id: 'micro_default' | 'small_default';
  model_type: 'qwen2';
  quantization_mode: 'weight_only_int4';
  context_length: number;
  bos_token_id: number | null;
  eos_token_id: number | number[] | null;
  pad_token_id: number | null;
  external_data_shards_allowed: boolean;
  graph_io_contract: Record<string, unknown>;
  artifacts: RuntimeManifestArtifactsV1;
  status: 'pending_real_weights' | 'verified';
}

export interface RuntimeManifestV1 {
  schema_version: 1;
  logical_pack_id: 'micro_default' | 'small_default';
  model_format: 'onnx';
  model_type: 'qwen2';
  quantization_mode: 'weight_only_int4';
  context_length: number;
  bos_token_id: number | null;
  eos_token_id: number | number[] | null;
  pad_token_id: number | null;
  external_data_shards_allowed: boolean;
  graph_io_contract: Record<string, unknown>;
  search_defaults: {
    do_sample: false;
    num_beams: 1;
    top_k: 1;
    top_p: 1.0;
    temperature: 1.0;
  };
  artifacts: RuntimeManifestArtifactsV1;
  status: 'pending_real_weights' | 'verified';
}

function assertSha256Maybe(value: string | undefined, field: string): void {
  if (value === undefined) return;
  if (!isValidSha256Hex(value)) {
    throw new Error(`RUNTIME_MANIFEST_INVALID_SHA256:${field}`);
  }
}

export function buildRuntimeManifestV1(
  input: RuntimeManifestBuildInputV1
): RuntimeManifestV1 {
  if (!input.graph_io_contract || typeof input.graph_io_contract !== 'object') {
    throw new Error('RUNTIME_MANIFEST_GRAPH_IO_CONTRACT_INVALID');
  }

  // required digest 3개 — undefined/빈 문자열 즉시 차단
  if (!input.artifacts.weights_digest_sha256) {
    throw new Error('RUNTIME_MANIFEST_WEIGHTS_DIGEST_REQUIRED');
  }
  if (!input.artifacts.tokenizer_digest_sha256) {
    throw new Error('RUNTIME_MANIFEST_TOKENIZER_DIGEST_REQUIRED');
  }
  if (!input.artifacts.chat_template_digest_sha256) {
    throw new Error('RUNTIME_MANIFEST_CHAT_TEMPLATE_DIGEST_REQUIRED');
  }

  // SHA-256 형식 검증 (required 3개 + optional 1개)
  assertSha256Maybe(input.artifacts.weights_digest_sha256, 'weights_digest_sha256');
  assertSha256Maybe(input.artifacts.tokenizer_digest_sha256, 'tokenizer_digest_sha256');
  assertSha256Maybe(input.artifacts.chat_template_digest_sha256, 'chat_template_digest_sha256');
  assertSha256Maybe(input.artifacts.config_digest_sha256, 'config_digest_sha256');
  return {
    schema_version: 1,
    logical_pack_id: input.logical_pack_id,
    model_format: 'onnx',
    model_type: input.model_type,
    quantization_mode: input.quantization_mode,
    context_length: input.context_length,
    bos_token_id: input.bos_token_id,
    eos_token_id: input.eos_token_id,
    pad_token_id: input.pad_token_id,
    external_data_shards_allowed: input.external_data_shards_allowed,
    graph_io_contract: input.graph_io_contract,
    search_defaults: {
      do_sample: false,
      num_beams: 1,
      top_k: 1,
      top_p: 1.0,
      temperature: 1.0,
    },
    artifacts: input.artifacts,
    status: input.status,
  };
}
