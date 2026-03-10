// AI-ALGO: RUNTIME_VARIANCE_SAMPLER_V1
// 알고리즘팀 산출물 — 런타임 분산 측정 (min 30샘플, p50/p95/p99)

export interface RuntimeSampleV1 {
  latency_ms: number;
  ttft_ms: number;
  decode_tps: number;
  rss_peak_mb: number;
  energy_proxy: number;
  thermal_degradation_pct: number;
}

export interface RuntimeVarianceSummaryV1 {
  logical_pack_id: string;
  device_class_id: string;
  sample_count: number;
  latency_mean_ms: number;
  latency_std_ms: number;
  latency_p50_ms: number;
  latency_p95_ms: number;
  latency_p99_ms: number;
  ttft_mean_ms: number;
  ttft_std_ms: number;
  decode_tps_mean: number;
  decode_tps_min: number;
  rss_peak_mean_mb: number;
  rss_peak_max_mb: number;
  energy_proxy_mean: number;
  thermal_degradation_pct: number;
}

const MIN_SAMPLES = 30;

function percentile(sorted: number[], p: number): number {
  const idx = Math.max(0, Math.min(sorted.length - 1, Math.floor((p / 100) * sorted.length) - 1));
  return sorted[idx];
}

function mean(values: number[]): number {
  return values.reduce((a, b) => a + b, 0) / values.length;
}

function stddev(values: number[], mu: number): number {
  if (values.length <= 1) return 0;
  const variance = values.reduce((a, b) => a + (b - mu) ** 2, 0) / values.length;
  return Math.sqrt(variance);
}

export function computeRuntimeVarianceSummaryV1(
  logical_pack_id: string,
  device_class_id: string,
  samples: RuntimeSampleV1[],
): RuntimeVarianceSummaryV1 {
  if (samples.length < MIN_SAMPLES)
    throw new Error(`RUNTIME_VARIANCE_INSUFFICIENT_SAMPLES:min=${MIN_SAMPLES}:got=${samples.length}`);

  const lat = samples.map(s => s.latency_ms).sort((a, b) => a - b);
  const ttft = samples.map(s => s.ttft_ms);
  const dps = samples.map(s => s.decode_tps);
  const rss = samples.map(s => s.rss_peak_mb);
  const energy = samples.map(s => s.energy_proxy);
  const thermal = samples.map(s => s.thermal_degradation_pct);

  const latMean = mean(lat);
  const ttftMean = mean(ttft);

  return {
    logical_pack_id,
    device_class_id,
    sample_count: samples.length,
    latency_mean_ms: latMean,
    latency_std_ms: stddev(lat, latMean),
    latency_p50_ms: percentile(lat, 50),
    latency_p95_ms: percentile(lat, 95),
    latency_p99_ms: percentile(lat, 99),
    ttft_mean_ms: ttftMean,
    ttft_std_ms: stddev(ttft, ttftMean),
    decode_tps_mean: mean(dps),
    decode_tps_min: Math.min(...dps),
    rss_peak_mean_mb: mean(rss),
    rss_peak_max_mb: Math.max(...rss),
    energy_proxy_mean: mean(energy),
    thermal_degradation_pct: mean(thermal),
  };
}

export function assertRuntimeVarianceSummaryV1(s: unknown): asserts s is RuntimeVarianceSummaryV1 {
  if (!s || typeof s !== 'object') throw new Error('RUNTIME_VARIANCE_SUMMARY_NOT_OBJECT');
  const r = s as Record<string, unknown>;
  if (typeof r['sample_count'] !== 'number' || (r['sample_count'] as number) < MIN_SAMPLES)
    throw new Error(`RUNTIME_VARIANCE_SAMPLE_COUNT_TOO_LOW:${r['sample_count']}`);
  if (typeof r['latency_p95_ms'] !== 'number')
    throw new Error('RUNTIME_VARIANCE_MISSING:latency_p95_ms');
  if (typeof r['decode_tps_min'] !== 'number')
    throw new Error('RUNTIME_VARIANCE_MISSING:decode_tps_min');
}
