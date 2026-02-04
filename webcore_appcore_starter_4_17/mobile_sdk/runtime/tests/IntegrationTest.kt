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
    } catch (e: Exception) {
        println("FAIL: ${e.message}")
        throw e
    }
}

