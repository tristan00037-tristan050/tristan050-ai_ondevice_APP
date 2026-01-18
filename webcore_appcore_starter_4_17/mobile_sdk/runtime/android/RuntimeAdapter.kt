/**
 * Runtime Adapter Interface
 * Abstraction for on-device ML runtime (offline-first, deterministic)
 */

package com.webcore.runtime

import com.webcore.perf.PerfMetrics

/**
 * Runtime adapter interface
 * Must support offline-first operation (no network required)
 */
interface RuntimeAdapter {
    /**
     * Load model from local storage
     * @param modelPath: Path to model file (local)
     * @return true if successful
     */
    fun loadModel(modelPath: String): Boolean

    /**
     * Run inference (deterministic for fixed model+input)
     * @param input: Input data (e.g., float array)
     * @return Inference result
     */
    fun infer(input: FloatArray): FloatArray?

    /**
     * Get performance metrics (meta-only, no user text)
     * @return Performance metrics
     */
    fun getPerfMetrics(): PerfMetrics

    /**
     * Release resources
     */
    fun release()
}

