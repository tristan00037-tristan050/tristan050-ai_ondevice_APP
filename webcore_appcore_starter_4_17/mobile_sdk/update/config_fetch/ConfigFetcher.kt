/**
 * Config Fetcher
 * Fetches configurations with ETag/TTL caching and attestation
 */

package com.webcore.mobile.update.config

import com.webcore.mobile.attestation.AttestationClient
import com.webcore.mobile.attestation.AttestationReasonCodes
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import java.io.File
import java.net.HttpURLConnection
import java.net.URL

/**
 * Config fetch result
 */
sealed class ConfigFetchResult {
    data class Success(val config: ByteArray, val etag: String?) : ConfigFetchResult()
    data class Failure(val reasonCode: String) : ConfigFetchResult()
}

/**
 * Config fetcher with attestation
 * Fail-closed: if attestation fails, fetch is blocked
 */
class ConfigFetcher(
    private val baseUrl: String,
    private val attestationClient: AttestationClient? = null
) {
    private var cachedEtag: String? = null
    
    /**
     * Fetch config with attestation
     * @param configPath Path to config resource
     * @param forceRefresh Force refresh (ignore cache)
     * @return ConfigFetchResult
     */
    suspend fun fetch(
        configPath: String,
        forceRefresh: Boolean = false
    ): ConfigFetchResult = withContext(Dispatchers.IO) {
        // Fail-closed: Obtain attestation token
        val (attestationToken, attestationReason) = attestationClient?.getTokenForRequest()
            ?: Pair(null, null)
        
        if (attestationToken == null && attestationClient != null) {
            // Attestation required but not available
            return@withContext ConfigFetchResult.Failure(
                attestationReason ?: AttestationReasonCodes.ATTESTATION_UNAVAILABLE
            )
        }
        
        try {
            val url = URL("$baseUrl/$configPath")
            val connection = url.openConnection() as HttpURLConnection
            
            // Set headers
            connection.setRequestProperty("Accept", "application/json")
            connection.setRequestProperty("If-None-Match", if (forceRefresh) null else cachedEtag)
            
            // Attach attestation token if available
            if (attestationToken != null) {
                connection.setRequestProperty("X-Attestation-Token", attestationToken)
            }
            
            connection.requestMethod = "GET"
            connection.connect()
            
            when (connection.responseCode) {
                200 -> {
                    val etag = connection.getHeaderField("ETag")
                    val config = connection.inputStream.readBytes()
                    cachedEtag = etag
                    ConfigFetchResult.Success(config, etag)
                }
                304 -> {
                    // Not modified (cache hit)
                    ConfigFetchResult.Success(ByteArray(0), cachedEtag)
                }
                else -> {
                    ConfigFetchResult.Failure("CONFIG_FETCH_HTTP_ERROR_${connection.responseCode}")
                }
            }
        } catch (e: Exception) {
            ConfigFetchResult.Failure("CONFIG_FETCH_ERROR")
        }
    }
    
    /**
     * Check if config fetch is allowed (attestation check)
     * @return true if fetch is allowed, false otherwise
     */
    suspend fun isFetchAllowed(): Boolean {
        return if (attestationClient != null) {
            attestationClient.isAvailable()
        } else {
            true // No attestation required
        }
    }
}
