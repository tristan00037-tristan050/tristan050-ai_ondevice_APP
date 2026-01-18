/**
 * Atomic Swap Tests
 * Verify atomic swap mechanism
 */

package com.webcore.update.swap

import com.webcore.update.storage.SecureStorage
import org.junit.Test
import org.junit.Assert.*
import java.io.File

class AtomicSwapTest {
    @Test
    fun testAtomicSwap() {
        val storageDir = File.createTempFile("test_storage", "").parentFile
        val secureStorage = SecureStorage(storageDir)
        val fileName = "test_config.json"

        // Stage content
        val content = "{\"config\": \"new\"}".toByteArray()
        val hash = secureStorage.calculateHash(content)
        val result = secureStorage.stage(content, expectedHash = hash, fileName = fileName)

        assertTrue("Staging should succeed", result.valid)

        // Perform atomic swap
        val atomicSwap = AtomicSwap(secureStorage, fileName)
        val swapResult = atomicSwap.swap()

        assertTrue("Atomic swap should succeed", swapResult.success)
        assertNotNull("Active path should be set", swapResult.activePath)

        // Verify active file exists
        val activePath = secureStorage.getActivePath(fileName)
        assertNotNull("Active file should exist", activePath)
        assertTrue("Active file should exist", File(activePath!!).exists())

        // Verify staged file is removed
        val stagedPath = secureStorage.getStagedPath(fileName)
        assertNull("Staged file should be removed", stagedPath)

        // Cleanup
        File(activePath).delete()
    }

    @Test
    fun testAtomicSwapWithBackup() {
        val storageDir = File.createTempFile("test_storage", "").parentFile
        val secureStorage = SecureStorage(storageDir)
        val fileName = "test_model.bin"

        // Create initial active file
        val activeDir = File(storageDir, "active")
        activeDir.mkdirs()
        val initialContent = "initial".toByteArray()
        File(activeDir, fileName).writeBytes(initialContent)

        // Stage new content
        val newContent = "new".toByteArray()
        val hash = secureStorage.calculateHash(newContent)
        secureStorage.stage(newContent, expectedHash = hash, fileName = fileName)

        // Perform atomic swap (should backup old file)
        val atomicSwap = AtomicSwap(secureStorage, fileName)
        val swapResult = atomicSwap.swap()

        assertTrue("Atomic swap should succeed", swapResult.success)

        // Verify backup exists
        val backupDir = File(storageDir, "backup")
        val backupFile = File(backupDir, fileName)
        assertTrue("Backup file should exist", backupFile.exists())

        // Verify active file has new content
        val activePath = secureStorage.getActivePath(fileName)
        assertNotNull("Active file should exist", activePath)
        val activeContent = File(activePath!!).readBytes()
        assertTrue("Active file should have new content", activeContent.contentEquals(newContent))

        // Cleanup
        File(activePath).delete()
        backupFile.delete()
    }
}

// Output-based proof
fun main() {
    val test = AtomicSwapTest()
    try {
        test.testAtomicSwap()
        test.testAtomicSwapWithBackup()
        println("ATOMIC_SWAP_OK=1")
    } catch (e: Exception) {
        println("FAIL: ${e.message}")
        throw e
    }
}

