/**
 * Performance Metrics (meta-only)
 * No user text, only numerical metrics
 */

package com.webcore.perf

/**
 * Performance metrics (meta-only)
 * Contains only numerical values, no raw text
 */
data class PerfMetrics(
    val inferenceCount: Int,
    val latencyP50Ms: Long,      // P50 latency in milliseconds
    val latencyP95Ms: Long,       // P95 latency in milliseconds
    val peakMemoryBytes: Long     // Peak memory usage in bytes
)

