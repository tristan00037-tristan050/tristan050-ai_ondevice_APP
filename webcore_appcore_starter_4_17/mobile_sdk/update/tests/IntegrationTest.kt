/**
 * Integration Tests
 * Run all tests and output proof metrics
 */

package com.webcore.update

import com.webcore.update.config.ConfigFetchTest
import com.webcore.update.swap.AtomicSwapTest
import com.webcore.update.storage.FailClosedTest

fun main() {
    val configTest = ConfigFetchTest()
    val swapTest = AtomicSwapTest()
    val failClosedTest = FailClosedTest()

    try {
        // Run config fetch tests
        configTest.testEtagCacheHit()

        // Run atomic swap tests
        swapTest.testAtomicSwap()
        swapTest.testAtomicSwapWithBackup()

        // Run fail-closed tests
        failClosedTest.testHashVerificationFailure()
        failClosedTest.testSignatureVerificationFailure()
        failClosedTest.testSwapFailsWithoutStagedFile()
        failClosedTest.testVerificationFailurePreventsSwap()

        // Output-based proof
        println("CACHE_ETAG_HIT_OK=1")
        println("ATOMIC_SWAP_OK=1")
        println("APPLY_FAILCLOSED_OK=1")
    } catch (e: Exception) {
        println("FAIL: ${e.message}")
        throw e
    }
}

