/**
 * Secure Storage
 * Verify hash/signature before storing
 */

package com.webcore.update.storage

import java.io.File
import java.security.MessageDigest
import javax.crypto.Mac
import javax.crypto.spec.SecretKeySpec

data class VerificationResult(
    val valid: Boolean,
    val reason: String? = null
)

/**
 * Secure storage with hash/signature verification
 * Fail-Closed: verification failure => never apply
 */
class SecureStorage(
    private val storageDir: File,
    private val secretKey: ByteArray? = null // For HMAC verification
) {
    private val stagedDir = File(storageDir, "staged")
    private val activeDir = File(storageDir, "active")
    private val backupDir = File(storageDir, "backup")

    init {
        stagedDir.mkdirs()
        activeDir.mkdirs()
        backupDir.mkdirs()
    }

    /**
     * Stage content with verification
     * Fail-Closed: verification failure => never stage
     */
    fun stage(
        content: ByteArray,
        expectedHash: String? = null,
        expectedSignature: String? = null,
        fileName: String
    ): VerificationResult {
        // Verify hash if provided
        if (expectedHash != null) {
            val actualHash = calculateHash(content)
            if (actualHash != expectedHash) {
                return VerificationResult(
                    valid = false,
                    reason = "Hash mismatch: expected $expectedHash, got $actualHash"
                )
            }
        }

        // Verify signature if provided
        if (expectedSignature != null && secretKey != null) {
            val actualSignature = calculateSignature(content, secretKey)
            if (actualSignature != expectedSignature) {
                return VerificationResult(
                    valid = false,
                    reason = "Signature mismatch"
                )
            }
        }

        // Stage content only if verification passes
        val stagedFile = File(stagedDir, fileName)
        stagedFile.writeBytes(content)

        // Store verification metadata
        if (expectedHash != null) {
            File(stagedDir, "$fileName.hash").writeText(expectedHash)
        }
        if (expectedSignature != null) {
            File(stagedDir, "$fileName.sig").writeText(expectedSignature)
        }

        return VerificationResult(valid = true)
    }

    /**
     * Get staged file path
     */
    fun getStagedPath(fileName: String): String? {
        val stagedFile = File(stagedDir, fileName)
        return if (stagedFile.exists()) stagedFile.absolutePath else null
    }

    /**
     * Get active file path
     */
    fun getActivePath(fileName: String): String? {
        val activeFile = File(activeDir, fileName)
        return if (activeFile.exists()) activeFile.absolutePath else null
    }

    /**
     * Backup active file before swap
     */
    fun backupActive(fileName: String): Boolean {
        val activeFile = File(activeDir, fileName)
        if (!activeFile.exists()) {
            return true // Nothing to backup
        }

        val backupFile = File(backupDir, fileName)
        return try {
            activeFile.copyTo(backupFile, overwrite = true)
            true
        } catch (e: Exception) {
            false
        }
    }

    /**
     * Restore from backup (rollback)
     */
    fun restoreFromBackup(fileName: String): Boolean {
        val backupFile = File(backupDir, fileName)
        if (!backupFile.exists()) {
            return false
        }

        val activeFile = File(activeDir, fileName)
        return try {
            backupFile.copyTo(activeFile, overwrite = true)
            true
        } catch (e: Exception) {
            false
        }
    }

    /**
     * Calculate SHA-256 hash
     */
    fun calculateHash(content: ByteArray): String {
        val digest = MessageDigest.getInstance("SHA-256")
        val hash = digest.digest(content)
        return hash.joinToString("") { "%02x".format(it) }
    }

    /**
     * Calculate HMAC-SHA256 signature
     */
    fun calculateSignature(content: ByteArray, key: ByteArray): String {
        val mac = Mac.getInstance("HmacSHA256")
        val secretKeySpec = SecretKeySpec(key, "HmacSHA256")
        mac.init(secretKeySpec)
        val signature = mac.doFinal(content)
        return signature.joinToString("") { "%02x".format(it) }
    }
}

