/**
 * Fail-Closed Tests
 * Verify verification failure => never apply
 */

package com.webcore.update.storage

import com.webcore.update.swap.AtomicSwap
import org.junit.Test
import org.junit.Assert.*
import java.io.File

class FailClosedTest {
    @Test
    fun testHashVerificationFailure() {
        val storageDir = File.createTempFile("test_storage", "").parentFile
        val secureStorage = SecureStorage(storageDir)
        val fileName = "test_config.json"

        // Stage content with wrong hash
        val content = "{\"config\": \"test\"}".toByteArray()
        val wrongHash = "wrong-hash"
        val result = secureStorage.stage(content, expectedHash = wrongHash, fileName = fileName)

        // Fail-Closed: verification failure => never stage
        assertFalse("Staging should fail with wrong hash", result.valid)
        assertNotNull("Reason should be provided", result.reason)

        // Verify file was not staged
        val stagedPath = secureStorage.getStagedPath(fileName)
        assertNull("Staged file should not exist", stagedPath)
    }

    @Test
    fun testSignatureVerificationFailure() {
        val storageDir = File.createTempFile("test_storage", "").parentFile
        val secretKey = "test-secret-key".toByteArray()
        val secureStorage = SecureStorage(storageDir, secretKey)
        val fileName = "test_model.bin"

        // Stage content with wrong signature
        val content = "model-content".toByteArray()
        val correctSignature = secureStorage.calculateSignature(content, secretKey)
        val wrongSignature = "wrong-signature"
        val result = secureStorage.stage(
            content,
            expectedSignature = wrongSignature,
            fileName = fileName
        )

        // Fail-Closed: verification failure => never stage
        assertFalse("Staging should fail with wrong signature", result.valid)
        assertNotNull("Reason should be provided", result.reason)

        // Verify file was not staged
        val stagedPath = secureStorage.getStagedPath(fileName)
        assertNull("Staged file should not exist", stagedPath)
    }

    @Test
    fun testSwapFailsWithoutStagedFile() {
        val storageDir = File.createTempFile("test_storage", "").parentFile
        val secureStorage = SecureStorage(storageDir)
        val fileName = "nonexistent.bin"

        // Try to swap without staged file
        val atomicSwap = AtomicSwap(secureStorage, fileName)
        val swapResult = atomicSwap.swap()

        // Fail-Closed: no staged file => swap fails
        assertFalse("Swap should fail without staged file", swapResult.success)
        assertNotNull("Error should be provided", swapResult.error)
    }

    @Test
    fun testVerificationFailurePreventsSwap() {
        val storageDir = File.createTempFile("test_storage", "").parentFile
        val secureStorage = SecureStorage(storageDir)
        val fileName = "test_config.json"

        // Stage content with verification failure
        val content = "{\"config\": \"test\"}".toByteArray()
        val wrongHash = "wrong-hash"
        val stageResult = secureStorage.stage(content, expectedHash = wrongHash, fileName = fileName)

        // Staging should fail
        assertFalse("Staging should fail", stageResult.valid)

        // Try to swap (should fail because no staged file)
        val atomicSwap = AtomicSwap(secureStorage, fileName)
        val swapResult = atomicSwap.swap()

        // Fail-Closed: verification failure => never apply
        assertFalse("Swap should fail", swapResult.success)
    }
}

// Output-based proof
fun main() {
    val test = FailClosedTest()
    try {
        test.testHashVerificationFailure()
        test.testSignatureVerificationFailure()
        test.testSwapFailsWithoutStagedFile()
        test.testVerificationFailurePreventsSwap()
        println("APPLY_FAILCLOSED_OK=1")
    } catch (e: Exception) {
        println("FAIL: ${e.message}")
        throw e
    }
}

