'use strict';

// P22-AI-03: DEVICE_PROFILE_METRICS_SSOT_V1
// Storage unit: cpu_time_us (microseconds) / latency_ns (nanoseconds)
// Display unit: ms only (converted at output layer)

export interface CpuSnapshot {
  /** Total user-mode CPU time in microseconds */
  user_us: bigint;
  /** Total system-mode CPU time in microseconds */
  system_us: bigint;
  /** Monotonic capture timestamp in nanoseconds */
  captured_at_ns: bigint;
}

const MAX_SAFE_BIGINT = BigInt(Number.MAX_SAFE_INTEGER);

function assertNonNegative(value: bigint, label: string): void {
  if (value < 0n) {
    throw new RangeError(`${label} must be non-negative, got ${value}`);
  }
}

function assertNoOverflow(value: bigint, label: string): void {
  if (value > MAX_SAFE_BIGINT) {
    throw new RangeError(
      `${label} exceeds MAX_SAFE_INTEGER (${value} > ${MAX_SAFE_BIGINT})`
    );
  }
}

/**
 * Capture a CPU snapshot using process.cpuUsage().
 * Stored as bigint microseconds to avoid float rounding.
 */
export function takeCpuSnapshot(): CpuSnapshot {
  const usage = process.cpuUsage();
  const captured_at_ns = process.hrtime.bigint();
  return {
    user_us: BigInt(usage.user),
    system_us: BigInt(usage.system),
    captured_at_ns,
  };
}

/**
 * Compute the CPU delta in milliseconds between two snapshots.
 * Throws on negative delta (clock went backwards).
 * Throws on overflow (value exceeds Number.MAX_SAFE_INTEGER).
 */
export function computeCpuDeltaMs(
  before: CpuSnapshot,
  after: CpuSnapshot
): number {
  const user_delta_us = after.user_us - before.user_us;
  const system_delta_us = after.system_us - before.system_us;

  if (user_delta_us < 0n) {
    throw new RangeError(
      `Negative user_us delta: ${user_delta_us}. Clock went backwards or snapshots are out of order.`
    );
  }
  if (system_delta_us < 0n) {
    throw new RangeError(
      `Negative system_us delta: ${system_delta_us}. Clock went backwards or snapshots are out of order.`
    );
  }

  const total_us = user_delta_us + system_delta_us;
  assertNoOverflow(total_us, 'cpu_time_us total');

  // Convert us → ms (divide by 1000)
  return Number(total_us) / 1000;
}

/**
 * Compute wall-clock latency in milliseconds between two snapshots.
 * Throws on negative delta (clock went backwards).
 * Throws on overflow (value exceeds Number.MAX_SAFE_INTEGER).
 */
export function computeLatencyMs(
  before: CpuSnapshot,
  after: CpuSnapshot
): number {
  const latency_ns = after.captured_at_ns - before.captured_at_ns;

  if (latency_ns < 0n) {
    throw new RangeError(
      `Negative latency_ns: ${latency_ns}. Clock went backwards or snapshots are out of order.`
    );
  }
  assertNonNegative(latency_ns, 'latency_ns');
  assertNoOverflow(latency_ns, 'latency_ns');

  // Convert ns → ms (divide by 1_000_000)
  return Number(latency_ns) / 1_000_000;
}
