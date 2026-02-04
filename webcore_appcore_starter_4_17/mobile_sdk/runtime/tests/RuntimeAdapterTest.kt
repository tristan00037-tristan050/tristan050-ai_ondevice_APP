/**
 * Runtime Adapter Tests
 * Verify offline-first, deterministic inference, and perf metrics
 */

package com.webcore.runtime

import com.webcore.perf.PerfMetrics
import org.junit.Test
import org.junit.Assert.*

class RuntimeAdapterTest {
    @Test
    fun testLoadModel() {
        val adapter = SimpleRuntimeAdapter()
        
        // Create a dummy model file for testing
        val modelPath = "/tmp/test_model.bin"
        val modelFile = java.io.File(modelPath)
        modelFile.createNewFile()
        
        val loaded = adapter.loadModel(modelPath)
        assertTrue("Model should load successfully", loaded)
        
        // Cleanup
        modelFile.delete()
        adapter.release()
    }

    @Test
    fun testDeterministicInference() {
        val adapter = SimpleRuntimeAdapter()
        
        // Create dummy model file
        val modelPath = "/tmp/test_model.bin"
        val modelFile = java.io.File(modelPath)
        modelFile.createNewFile()
        adapter.loadModel(modelPath)
        
        // Same input should produce same output (deterministic)
        val input1 = floatArrayOf(1.0f, 2.0f, 3.0f)
        val input2 = floatArrayOf(1.0f, 2.0f, 3.0f)
        
        val output1 = adapter.infer(input1)
        val output2 = adapter.infer(input2)
        
        assertNotNull("Output should not be null", output1)
        assertNotNull("Output should not be null", output2)
        assertArrayEquals(
            "Same input should produce same output (deterministic)",
            output1,
            output2,
            0.001f
        )
        
        // Cleanup
        modelFile.delete()
        adapter.release()
    }

    @Test
    fun testPerfMetrics() {
        val adapter = SimpleRuntimeAdapter()
        
        // Create dummy model file
        val modelPath = "/tmp/test_model.bin"
        val modelFile = java.io.File(modelPath)
        modelFile.createNewFile()
        adapter.loadModel(modelPath)
        
        // Run multiple inferences to generate perf data
        val input = floatArrayOf(1.0f, 2.0f, 3.0f)
        for (i in 1..10) {
            adapter.infer(input)
            Thread.sleep(10) // Simulate some latency variation
        }
        
        val metrics = adapter.getPerfMetrics()
        
        // Verify perf metrics are present
        assertTrue("Inference count should be > 0", metrics.inferenceCount > 0)
        assertTrue("P50 latency should be present", metrics.latencyP50Ms >= 0)
        assertTrue("P95 latency should be present", metrics.latencyP95Ms >= 0)
        assertTrue("Peak memory should be present", metrics.peakMemoryBytes >= 0)
        
        // Verify P95 >= P50
        assertTrue("P95 should be >= P50", metrics.latencyP95Ms >= metrics.latencyP50Ms)
        
        // Cleanup
        modelFile.delete()
        adapter.release()
    }

    @Test
    fun testOfflineFirst() {
        val adapter = SimpleRuntimeAdapter()
        
        // Model should load from local file (no network)
        val modelPath = "/tmp/test_model.bin"
        val modelFile = java.io.File(modelPath)
        modelFile.createNewFile()
        
        // Load model (offline)
        val loaded = adapter.loadModel(modelPath)
        assertTrue("Model should load offline", loaded)
        
        // Inference should work offline
        val input = floatArrayOf(1.0f, 2.0f, 3.0f)
        val output = adapter.infer(input)
        assertNotNull("Inference should work offline", output)
        
        // Cleanup
        modelFile.delete()
        adapter.release()
    }
}

// Output-based proof
fun main() {
    val test = RuntimeAdapterTest()
    
    // Run tests
    try {
        test.testLoadModel()
        test.testDeterministicInference()
        test.testPerfMetrics()
        test.testOfflineFirst()
    } catch (e: Exception) {
        println("FAIL: ${e.message}")
        throw e
    }
}

