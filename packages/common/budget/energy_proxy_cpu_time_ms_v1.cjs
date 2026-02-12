"use strict";

/**
 * energy_proxy_cpu_time_ms_v1
 * - source of truth
 * - uses process.cpuUsage() (microseconds)
 * - returns ms as float (no rounding)
 */
function cpuTimeMsV1() {
  const u = process.cpuUsage(); // { user, system } in microseconds
  const totalUs = (u.user || 0) + (u.system || 0);
  return totalUs / 1000.0;
}

module.exports = { cpuTimeMsV1 };

