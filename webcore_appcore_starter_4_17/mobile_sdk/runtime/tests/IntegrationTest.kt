/**
 * Integration Tests
 * Run all tests and output proof metrics
 */

package com.webcore.runtime

import com.webcore.perf.PerfMetricsTest

fun main() {
    val runtimeTest = RuntimeAdapterTest()
    val perfTest = PerfMetricsTest()
    
    try {
        // Run runtime tests
        runtimeTest.testLoadModel()
        runtimeTest.testDeterministicInference()
        runtimeTest.testPerfMetrics()
        runtimeTest.testOfflineFirst()
        
        // Run perf metrics tests
        perfTest.testPerfMetricsMetaOnly()
        perfTest.testPerfMetricsP50P95Present()
        perfTest.testPerfMetricsPeakMemoryPresent()
        
        // Output-based proof
        println("ONDEVICE_INFER_OK=1")
        println("PERF_P50_P95_KEYS_PRESENT=1")
        println("PERF_MEMORY_PEAK_KEY_PRESENT=1")
    } catch (e: Exception) {
        println("FAIL: ${e.message}")
        throw e
    }
}

