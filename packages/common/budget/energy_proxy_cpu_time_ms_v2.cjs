"use strict";

/**
 * energy_proxy_cpu_time_ms_v2
 * - single source of truth (v2)
 * - uses process.cpuUsage() (microseconds), returns ms as float
 */
function cpuTimeMsV2() {
  const u = process.cpuUsage();
  const totalUs = (u.user || 0) + (u.system || 0);
  return totalUs / 1000.0;
}

module.exports = { cpuTimeMsV2 };
