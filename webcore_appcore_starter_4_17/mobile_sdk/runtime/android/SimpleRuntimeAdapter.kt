/**
 * Simple Runtime Adapter Implementation
 * End-to-end implementation: load + infer with perf metrics
 */

package com.webcore.runtime

import com.webcore.perf.PerfMetrics
import java.io.File
import kotlin.system.measureTimeMillis

/**
 * Simple runtime adapter (mock implementation for demonstration)
 * In production, this would use actual ML runtime (TensorFlow Lite, ONNX Runtime, etc.)
 */
class SimpleRuntimeAdapter : RuntimeAdapter {
    private var modelLoaded = false
    private var inferenceCount = 0
    private val inferenceLatencies = mutableListOf<Long>()
    private var peakMemoryBytes: Long = 0

    override fun loadModel(modelPath: String): Boolean {
        // Offline-first: load from local file
        val modelFile = File(modelPath)
        if (!modelFile.exists()) {
            return false
        }

        // Simulate model loading
        val loadTime = measureTimeMillis {
            // In production: actual model loading
            // e.g., TensorFlow Lite: Interpreter(modelFile)
            Thread.sleep(50) // Simulate loading time
        }

        modelLoaded = true
        return true
    }

    override fun infer(input: FloatArray): FloatArray? {
        if (!modelLoaded) {
            return null
        }

        // Deterministic inference: same input => same output
        val (result, latency) = measureInference {
            // Simulate inference (deterministic)
            // In production: actual inference
            // e.g., interpreter.run(input, output)
            val output = FloatArray(input.size) { index ->
                // Deterministic transformation
                input[index] * 0.5f + 0.1f
            }
            output
        }

        inferenceCount++
        inferenceLatencies.add(latency)

        // Track peak memory (simulated)
        val currentMemory = Runtime.getRuntime().let { it.totalMemory() - it.freeMemory() }
        if (currentMemory > peakMemoryBytes) {
            peakMemoryBytes = currentMemory
        }

        return result
    }

    override fun getPerfMetrics(): PerfMetrics {
        val sortedLatencies = inferenceLatencies.sorted()

        // Calculate P50 and P95
        val p50 = if (sortedLatencies.isNotEmpty()) {
            sortedLatencies[sortedLatencies.size / 2]
        } else {
            0L
        }

        val p95 = if (sortedLatencies.isNotEmpty()) {
            sortedLatencies[(sortedLatencies.size * 95) / 100]
        } else {
            0L
        }

        return PerfMetrics(
            inferenceCount = inferenceCount,
            latencyP50Ms = p50,
            latencyP95Ms = p95,
            peakMemoryBytes = peakMemoryBytes
        )
    }

    override fun release() {
        modelLoaded = false
        inferenceCount = 0
        inferenceLatencies.clear()
        peakMemoryBytes = 0
    }

    /**
     * Measure inference latency
     */
    private fun <T> measureInference(block: () -> T): Pair<T, Long> {
        var result: T
        val latency = measureTimeMillis {
            result = block()
        }
        return Pair(result, latency)
    }
}

