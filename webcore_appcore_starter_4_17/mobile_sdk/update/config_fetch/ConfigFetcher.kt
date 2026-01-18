/**
 * Config Fetcher
 * Fetch config with ETag/TTL support
 */

package com.webcore.update.config

import java.io.File
import java.net.HttpURLConnection
import java.net.URL
import java.util.concurrent.TimeUnit

data class FetchResult(
    val success: Boolean,
    val content: ByteArray? = null,
    val etag: String? = null,
    val ttlSeconds: Long? = null,
    val cached: Boolean = false,
    val error: String? = null
)

/**
 * Config fetcher with ETag/TTL cache support
 */
class ConfigFetcher(
    private val cacheDir: File,
    private val defaultTtlSeconds: Long = 3600 // 1 hour
) {
    private val cacheFile = File(cacheDir, "config_cache.json")
    private val etagFile = File(cacheDir, "config_etag.txt")
    private val ttlFile = File(cacheDir, "config_ttl.txt")

    /**
     * Fetch config from URL with ETag/TTL cache
     */
    fun fetch(url: String): FetchResult {
        try {
            // Check cache first
            if (cacheFile.exists() && etagFile.exists() && ttlFile.exists()) {
                val cachedEtag = etagFile.readText().trim()
                val cachedTtl = ttlFile.readText().trim().toLongOrNull() ?: 0L
                val cacheTime = cacheFile.lastModified()
                val now = System.currentTimeMillis()
                val ageSeconds = (now - cacheTime) / 1000

                // Check if cache is still valid (TTL)
                if (ageSeconds < cachedTtl) {
                    // Cache hit - return cached content
                    val cachedContent = cacheFile.readBytes()
                    return FetchResult(
                        success = true,
                        content = cachedContent,
                        etag = cachedEtag,
                        ttlSeconds = cachedTtl - ageSeconds,
                        cached = true
                    )
                }

                // Cache expired - fetch with If-None-Match
                val connection = URL(url).openConnection() as HttpURLConnection
                connection.setRequestProperty("If-None-Match", cachedEtag)
                connection.connectTimeout = 5000
                connection.readTimeout = 10000

                val responseCode = connection.responseCode

                if (responseCode == HttpURLConnection.HTTP_NOT_MODIFIED) {
                    // 304 Not Modified - cache is still valid
                    val cachedContent = cacheFile.readBytes()
                    val newTtl = connection.getHeaderField("Cache-Control")?.let { parseTtl(it) } ?: defaultTtlSeconds
                    updateCache(cachedContent, cachedEtag, newTtl)
                    return FetchResult(
                        success = true,
                        content = cachedContent,
                        etag = cachedEtag,
                        ttlSeconds = newTtl,
                        cached = true
                    )
                }
            }

            // Fetch fresh content
            val connection = URL(url).openConnection() as HttpURLConnection
            connection.connectTimeout = 5000
            connection.readTimeout = 10000

            val responseCode = connection.responseCode
            if (responseCode != HttpURLConnection.HTTP_OK) {
                return FetchResult(
                    success = false,
                    error = "HTTP $responseCode"
                )
            }

            val content = connection.inputStream.readBytes()
            val etag = connection.getHeaderField("ETag")?.removeSurrounding("\"")
            val ttl = connection.getHeaderField("Cache-Control")?.let { parseTtl(it) } ?: defaultTtlSeconds

            // Update cache
            updateCache(content, etag, ttl)

            return FetchResult(
                success = true,
                content = content,
                etag = etag,
                ttlSeconds = ttl,
                cached = false
            )
        } catch (e: Exception) {
            // Offline resilience: return cached content if available
            if (cacheFile.exists()) {
                val cachedContent = cacheFile.readBytes()
                val cachedEtag = if (etagFile.exists()) etagFile.readText().trim() else null
                return FetchResult(
                    success = true,
                    content = cachedContent,
                    etag = cachedEtag,
                    ttlSeconds = null,
                    cached = true
                )
            }

            return FetchResult(
                success = false,
                error = e.message
            )
        }
    }

    private fun updateCache(content: ByteArray, etag: String?, ttl: Long) {
        cacheFile.writeBytes(content)
        if (etag != null) {
            etagFile.writeText(etag)
        }
        ttlFile.writeText(ttl.toString())
    }

    private fun parseTtl(cacheControl: String): Long {
        // Parse "max-age=3600" format
        val maxAgeMatch = Regex("max-age=(\\d+)").find(cacheControl)
        return maxAgeMatch?.groupValues?.get(1)?.toLongOrNull() ?: defaultTtlSeconds
    }
}

