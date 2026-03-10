// AI-ALGO: MODEL_PACK_CATALOG_V1
// 알고리즘팀 산출물 — 모델팩 빌드 스펙 (PackBuildSpecV1, SLO, 아티팩트 목록)

export type QuantizationMode = 'weight_only_int4';
export type PackStatus = 'pending_real_weights' | 'verified';

export interface SloContractV1 {
  ram_limit_mb: number;
  latency_p95_ms: number;
  decode_tps_min: number;
  prompt_budget_tokens: number;
  generation_budget_tokens: number;
  thermal_headroom_min: number;
  sustained_minutes: number;
}

export interface PackBuildSpecV1 {
  logical_pack_id: string;
  base_model: string;
  quantization_mode: QuantizationMode;
  context_length: number;
  slo: SloContractV1;
  required_artifacts: string[];
  status: PackStatus;
}

export const MODEL_PACK_CATALOG_V1: PackBuildSpecV1[] = [
  {
    logical_pack_id: 'micro_default',
    base_model: 'Qwen2.5-1.5B-Instruct',
    quantization_mode: 'weight_only_int4',
    context_length: 8192,
    slo: {
      ram_limit_mb: 1536,
      latency_p95_ms: 1200,
      decode_tps_min: 8,
      prompt_budget_tokens: 512,
      generation_budget_tokens: 128,
      thermal_headroom_min: 0.6,
      sustained_minutes: 10,
    },
    required_artifacts: [
      'model.onnx',
      'tokenizer.json',
      'config.json',
      'chat_template.jinja',
      'runtime_manifest.json',
      'SHA256SUMS',
    ],
    status: 'pending_real_weights',
  },
  {
    logical_pack_id: 'small_default',
    base_model: 'Qwen2.5-3B-Instruct',
    quantization_mode: 'weight_only_int4',
    context_length: 8192,
    slo: {
      ram_limit_mb: 3072,
      latency_p95_ms: 2000,
      decode_tps_min: 8,
      prompt_budget_tokens: 512,
      generation_budget_tokens: 128,
      thermal_headroom_min: 0.6,
      sustained_minutes: 10,
    },
    required_artifacts: [
      'model.onnx',
      'tokenizer.json',
      'config.json',
      'chat_template.jinja',
      'runtime_manifest.json',
      'SHA256SUMS',
    ],
    status: 'pending_real_weights',
  },
];

export function getPackSpec(logical_pack_id: string): PackBuildSpecV1 {
  const spec = MODEL_PACK_CATALOG_V1.find(p => p.logical_pack_id === logical_pack_id);
  if (!spec) throw new Error(`PACK_NOT_IN_CATALOG:${logical_pack_id}`);
  return spec;
}
