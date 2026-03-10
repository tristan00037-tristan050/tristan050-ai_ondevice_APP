// AI-ALGO: MODEL_PACK_DIGEST_V1
// 알고리즘팀 산출물 — logical/tokenizer/pack identity digest 빌더

import { typedDigest } from '../crypto/digest_v1.ts';

export interface LogicalPackIdentityV1 {
  logical_pack_id: string;
  base_model: string;
  quantization_mode: string;
  context_length: number;
}

export interface TokenizerIdentityV1 {
  tokenizer_json_digest_sha256: string;
  chat_template_digest_sha256: string;
  vocab_size: number;
}

export interface CompiledPackIdentityV1 {
  logical_pack_digest: string;
  model_onnx_digest_sha256: string;
  runtime_version: string;
  device_class_id: string;
}

export function buildLogicalPackDigestV1(identity: LogicalPackIdentityV1): string {
  return typedDigest('logical-pack', 'v1', identity);
}

export function buildTokenizerDigestV1(identity: TokenizerIdentityV1): string {
  return typedDigest('tokenizer-identity', 'v1', identity);
}

export function buildCompiledPackDigestV1(identity: CompiledPackIdentityV1): string {
  return typedDigest('compiled-pack', 'v1', identity);
}
