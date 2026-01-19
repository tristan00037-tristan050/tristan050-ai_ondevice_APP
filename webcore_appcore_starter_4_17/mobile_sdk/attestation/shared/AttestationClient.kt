/**
 * Attestation Client
 * Manages attestation token acquisition and attachment to requests
 */

package com.webcore.mobile.attestation

/**
 * Attestation client
 * Fail-closed: if attestation cannot be obtained, requests are blocked
 */
class AttestationClient(
    private val provider: AttestationProvider
) {
    /**
     * Get attestation token for request
     * @return Pair of (token: String?, reasonCode: String?)
     *   - If success: (token, null)
     *   - If failure: (null, reasonCode)
     */
    suspend fun getTokenForRequest(): Pair<String?, String?> {
        return when (val result = provider.obtainToken()) {
            is AttestationResult.Success -> Pair(result.token, null)
            is AttestationResult.Failure -> Pair(null, result.reasonCode)
        }
    }
    
    /**
     * Check if attestation is available (non-blocking check)
     * @return true if attestation can be obtained, false otherwise
     */
    suspend fun isAvailable(): Boolean {
        return when (provider.obtainToken()) {
            is AttestationResult.Success -> true
            is AttestationResult.Failure -> false
        }
    }
}

