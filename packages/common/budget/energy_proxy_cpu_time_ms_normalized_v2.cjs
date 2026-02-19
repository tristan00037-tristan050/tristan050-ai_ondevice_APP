'use strict';

/**
 * normalized v2:
 * - cpu_time_ms = (user_us + system_us)/1000.0
 * - normalized_cpu_time_ms = cpu_time_ms / inference_count
 * fail-closed:
 * - inference_count <= 0 -> throw
 * - non-finite -> throw
 */
function cpuTimeMsFromUsage(us) {
  if (!us || typeof us !== 'object') throw new Error('ENERGY_PROXY_BAD_USAGE');
  const user = Number(us.user);
  const system = Number(us.system);
  if (!Number.isFinite(user) || !Number.isFinite(system)) throw new Error('ENERGY_PROXY_NONFINITE_US');
  const ms = (user + system) / 1000.0;
  if (!Number.isFinite(ms) || ms <= 0) throw new Error('ENERGY_PROXY_MS_NONPOSITIVE');
  return ms;
}

function normalizedCpuTimeMsV2(usage_us, inference_count) {
  const n = Number(inference_count);
  if (!Number.isFinite(n) || n <= 0) throw new Error('ENERGY_PROXY_BAD_INFERENCE_COUNT');
  const ms = cpuTimeMsFromUsage(usage_us);
  const norm = ms / n;
  if (!Number.isFinite(norm) || norm <= 0) throw new Error('ENERGY_PROXY_NORM_NONPOSITIVE');
  return { cpu_time_ms: ms, normalized_cpu_time_ms: norm, inference_count: n };
}

module.exports = { normalizedCpuTimeMsV2, cpuTimeMsFromUsage };
