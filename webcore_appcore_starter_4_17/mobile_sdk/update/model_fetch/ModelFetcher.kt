/**
 * Model Fetcher
 * Fetches ML models with ETag/TTL caching and attestation
 */

package com.webcore.mobile.update.model

import com.webcore.mobile.attestation.AttestationClient
import com.webcore.mobile.attestation.AttestationReasonCodes
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import java.io.File
import java.net.HttpURLConnection
import java.net.URL

/**
 * Model fetch result
 */
sealed class ModelFetchResult {
    data class Success(val modelData: ByteArray, val etag: String?, val sha256: String?) : ModelFetchResult()
    data class Failure(val reasonCode: String) : ModelFetchResult()
}

/**
 * Model fetcher with attestation
 * Fail-closed: if attestation fails, fetch is blocked
 */
class ModelFetcher(
    private val baseUrl: String,
    private val attestationClient: AttestationClient? = null
) {
    private var cachedEtag: String? = null
    
    /**
     * Fetch model with attestation
     * @param modelPath Path to model resource
     * @param forceRefresh Force refresh (ignore cache)
     * @return ModelFetchResult
     */
    suspend fun fetch(
        modelPath: String,
        forceRefresh: Boolean = false
    ): ModelFetchResult = withContext(Dispatchers.IO) {
        // Fail-closed: Obtain attestation token
        val (attestationToken, attestationReason) = attestationClient?.getTokenForRequest()
            ?: Pair(null, null)
        
        if (attestationToken == null && attestationClient != null) {
            // Attestation required but not available
            return@withContext ModelFetchResult.Failure(
                attestationReason ?: AttestationReasonCodes.ATTESTATION_UNAVAILABLE
            )
        }
        
        try {
            val url = URL("$baseUrl/$modelPath")
            val connection = url.openConnection() as HttpURLConnection
            
            // Set headers
            connection.setRequestProperty("Accept", "application/octet-stream")
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
                    val sha256 = connection.getHeaderField("X-Model-SHA256")
                    val modelData = connection.inputStream.readBytes()
                    cachedEtag = etag
                    ModelFetchResult.Success(modelData, etag, sha256)
                }
                304 -> {
                    // Not modified (cache hit)
                    ModelFetchResult.Success(ByteArray(0), cachedEtag, null)
                }
                else -> {
                    ModelFetchResult.Failure("MODEL_FETCH_HTTP_ERROR_${connection.responseCode}")
                }
            }
        } catch (e: Exception) {
            ModelFetchResult.Failure("MODEL_FETCH_ERROR")
        }
    }
    
    /**
     * Check if model fetch is allowed (attestation check)
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
