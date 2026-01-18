/**
 * Atomic Swap
 * Atomic swap mechanism: no partial state visible to inference path
 */

package com.webcore.update.swap

import com.webcore.update.storage.SecureStorage
import java.io.File

data class SwapResult(
    val success: Boolean,
    val activePath: String? = null,
    val error: String? = null
)

/**
 * Atomic swap manager
 * Ensures no partial state is visible to inference path
 */
class AtomicSwap(
    private val secureStorage: SecureStorage,
    private val fileName: String
) {
    /**
     * Perform atomic swap
     * Fail-Closed: verification failure => never swap
     */
    fun swap(): SwapResult {
        try {
            // Get staged file
            val stagedPath = secureStorage.getStagedPath(fileName)
            if (stagedPath == null) {
                return SwapResult(
                    success = false,
                    error = "No staged file found"
                )
            }

            val stagedFile = File(stagedPath)
            if (!stagedFile.exists()) {
                return SwapResult(
                    success = false,
                    error = "Staged file does not exist"
                )
            }

            // Backup current active file (for rollback)
            val activePath = secureStorage.getActivePath(fileName)
            if (activePath != null) {
                if (!secureStorage.backupActive(fileName)) {
                    return SwapResult(
                        success = false,
                        error = "Failed to backup active file"
                    )
                }
            }

            // Atomic swap: move staged to active
            // Use rename which is atomic on most filesystems
            val activeDir = File(secureStorage.storageDir, "active")
            val activeFile = File(activeDir, fileName)
            val tempActiveFile = File(activeDir, "$fileName.tmp")

            // Write to temp file first
            stagedFile.copyTo(tempActiveFile, overwrite = true)

            // Atomic rename: temp -> active
            // This is atomic on most filesystems (no partial state visible)
            val renamed = tempActiveFile.renameTo(activeFile)
            if (!renamed) {
                // Cleanup temp file
                tempActiveFile.delete()
                return SwapResult(
                    success = false,
                    error = "Failed to perform atomic swap"
                )
            }

            // Cleanup staged file
            stagedFile.delete()

            return SwapResult(
                success = true,
                activePath = activeFile.absolutePath
            )
        } catch (e: Exception) {
            return SwapResult(
                success = false,
                error = e.message
            )
        }
    }

    /**
     * Rollback to previous version
     */
    fun rollback(): SwapResult {
        try {
            val restored = secureStorage.restoreFromBackup(fileName)
            if (!restored) {
                return SwapResult(
                    success = false,
                    error = "No backup found for rollback"
                )
            }

            val activePath = secureStorage.getActivePath(fileName)
            return SwapResult(
                success = true,
                activePath = activePath
            )
        } catch (e: Exception) {
            return SwapResult(
                success = false,
                error = e.message
            )
        }
    }
}

