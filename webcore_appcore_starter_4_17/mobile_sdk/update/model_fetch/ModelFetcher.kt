/**
 * Model Fetcher
 * Fetch model with ETag/TTL support
 */

package com.webcore.update.model

import java.io.File
import java.net.HttpURLConnection
import java.net.URL

data class ModelFetchResult(
    val success: Boolean,
    val modelPath: String? = null,
    val etag: String? = null,
    val ttlSeconds: Long? = null,
    val cached: Boolean = false,
    val error: String? = null
)

/**
 * Model fetcher with ETag/TTL cache support
 */
class ModelFetcher(
    private val cacheDir: File,
    private val defaultTtlSeconds: Long = 86400 // 24 hours
) {
    private val modelCacheDir = File(cacheDir, "models")
    private val etagFile = File(cacheDir, "model_etag.txt")
    private val ttlFile = File(cacheDir, "model_ttl.txt")

    init {
        modelCacheDir.mkdirs()
    }

    /**
     * Fetch model from URL with ETag/TTL cache
     */
    fun fetch(url: String, modelId: String): ModelFetchResult {
        try {
            val cachedModelFile = File(modelCacheDir, "$modelId.bin")
            val cachedEtagFile = File(modelCacheDir, "$modelId.etag")

            // Check cache first
            if (cachedModelFile.exists() && cachedEtagFile.exists()) {
                val cachedEtag = cachedEtagFile.readText().trim()
                val cachedTtl = if (ttlFile.exists()) ttlFile.readText().trim().toLongOrNull() ?: 0L else 0L
                val cacheTime = cachedModelFile.lastModified()
                val now = System.currentTimeMillis()
                val ageSeconds = (now - cacheTime) / 1000

                // Check if cache is still valid (TTL)
                if (ageSeconds < cachedTtl) {
                    // Cache hit - return cached model
                    return ModelFetchResult(
                        success = true,
                        modelPath = cachedModelFile.absolutePath,
                        etag = cachedEtag,
                        ttlSeconds = cachedTtl - ageSeconds,
                        cached = true
                    )
                }

                // Cache expired - fetch with If-None-Match
                val connection = URL(url).openConnection() as HttpURLConnection
                connection.setRequestProperty("If-None-Match", cachedEtag)
                connection.connectTimeout = 10000
                connection.readTimeout = 30000

                val responseCode = connection.responseCode

                if (responseCode == HttpURLConnection.HTTP_NOT_MODIFIED) {
                    // 304 Not Modified - cache is still valid
                    val newTtl = connection.getHeaderField("Cache-Control")?.let { parseTtl(it) } ?: defaultTtlSeconds
                    updateCache(cachedModelFile, cachedEtag, newTtl)
                    return ModelFetchResult(
                        success = true,
                        modelPath = cachedModelFile.absolutePath,
                        etag = cachedEtag,
                        ttlSeconds = newTtl,
                        cached = true
                    )
                }
            }

            // Fetch fresh model
            val connection = URL(url).openConnection() as HttpURLConnection
            connection.connectTimeout = 10000
            connection.readTimeout = 30000

            val responseCode = connection.responseCode
            if (responseCode != HttpURLConnection.HTTP_OK) {
                return ModelFetchResult(
                    success = false,
                    error = "HTTP $responseCode"
                )
            }

            // Download to temporary file first
            val tempFile = File(modelCacheDir, "$modelId.tmp")
            connection.inputStream.use { input ->
                tempFile.outputStream().use { output ->
                    input.copyTo(output)
                }
            }

            val etag = connection.getHeaderField("ETag")?.removeSurrounding("\"")
            val ttl = connection.getHeaderField("Cache-Control")?.let { parseTtl(it) } ?: defaultTtlSeconds

            // Move temp file to final location (atomic)
            val finalFile = File(modelCacheDir, "$modelId.bin")
            tempFile.renameTo(finalFile)

            // Update cache metadata
            if (etag != null) {
                cachedEtagFile.writeText(etag)
            }
            ttlFile.writeText(ttl.toString())

            return ModelFetchResult(
                success = true,
                modelPath = finalFile.absolutePath,
                etag = etag,
                ttlSeconds = ttl,
                cached = false
            )
        } catch (e: Exception) {
            // Offline resilience: return cached model if available
            val cachedModelFile = File(modelCacheDir, "$modelId.bin")
            if (cachedModelFile.exists()) {
                val cachedEtag = if (File(modelCacheDir, "$modelId.etag").exists()) {
                    File(modelCacheDir, "$modelId.etag").readText().trim()
                } else {
                    null
                }
                return ModelFetchResult(
                    success = true,
                    modelPath = cachedModelFile.absolutePath,
                    etag = cachedEtag,
                    ttlSeconds = null,
                    cached = true
                )
            }

            return ModelFetchResult(
                success = false,
                error = e.message
            )
        }
    }

    private fun updateCache(modelFile: File, etag: String?, ttl: Long) {
        if (etag != null) {
            File(modelCacheDir, "${modelFile.nameWithoutExtension}.etag").writeText(etag)
        }
        ttlFile.writeText(ttl.toString())
    }

    private fun parseTtl(cacheControl: String): Long {
        val maxAgeMatch = Regex("max-age=(\\d+)").find(cacheControl)
        return maxAgeMatch?.groupValues?.get(1)?.toLongOrNull() ?: defaultTtlSeconds
    }
}

