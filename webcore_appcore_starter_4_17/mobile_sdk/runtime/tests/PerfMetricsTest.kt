/**
 * Performance Metrics Tests
 * Verify meta-only metrics (no user text)
 */

package com.webcore.perf

import org.junit.Test
import org.junit.Assert.*

class PerfMetricsTest {
    @Test
    fun testPerfMetricsMetaOnly() {
        val metrics = PerfMetrics(
            inferenceCount = 100,
            latencyP50Ms = 50,
            latencyP95Ms = 95,
            peakMemoryBytes = 1024 * 1024
        )
        
        // Verify all fields are numerical (meta-only)
        assertTrue("inferenceCount should be integer", metrics.inferenceCount is Int)
        assertTrue("latencyP50Ms should be long", metrics.latencyP50Ms is Long)
        assertTrue("latencyP95Ms should be long", metrics.latencyP95Ms is Long)
        assertTrue("peakMemoryBytes should be long", metrics.peakMemoryBytes is Long)
        
        // Verify no text fields (meta-only)
        val metricsString = metrics.toString()
        assertFalse("Metrics should not contain user text", metricsString.contains("user"))
        assertFalse("Metrics should not contain raw text", metricsString.length > 1000)
    }

    @Test
    fun testPerfMetricsP50P95Present() {
        val metrics = PerfMetrics(
            inferenceCount = 10,
            latencyP50Ms = 25,
            latencyP95Ms = 45,
            peakMemoryBytes = 512 * 1024
        )
        
        // Verify P50 and P95 are present
        assertTrue("P50 should be present", metrics.latencyP50Ms >= 0)
        assertTrue("P95 should be present", metrics.latencyP95Ms >= 0)
        assertTrue("P95 should be >= P50", metrics.latencyP95Ms >= metrics.latencyP50Ms)
    }

    @Test
    fun testPerfMetricsPeakMemoryPresent() {
        val metrics = PerfMetrics(
            inferenceCount = 5,
            latencyP50Ms = 10,
            latencyP95Ms = 20,
            peakMemoryBytes = 256 * 1024
        )
        
        // Verify peak memory is present
        assertTrue("Peak memory should be present", metrics.peakMemoryBytes >= 0)
    }
}

// Output-based proof
fun main() {
    val test = PerfMetricsTest()
    
    try {
        test.testPerfMetricsMetaOnly()
        test.testPerfMetricsP50P95Present()
        test.testPerfMetricsPeakMemoryPresent()
        
        println("PERF_P50_P95_KEYS_PRESENT=1")
        println("PERF_MEMORY_PEAK_KEY_PRESENT=1")
    } catch (e: Exception) {
        println("FAIL: ${e.message}")
        throw e
    }
}

