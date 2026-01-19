/**
 * Attestation Provider Interface
 * Pluggable attestation token acquisition
 */

package com.webcore.mobile.attestation

/**
 * Attestation result
 */
sealed class AttestationResult {
    data class Success(val token: String) : AttestationResult()
    data class Failure(val reasonCode: String) : AttestationResult()
}

/**
 * Attestation Provider interface
 * Platform-specific implementations (Android Play Integrity, iOS App Attest, etc.)
 */
interface AttestationProvider {
    /**
     * Obtain attestation token
     * @return AttestationResult.Success with token, or AttestationResult.Failure with reason code
     */
    suspend fun obtainToken(): AttestationResult
}

/**
 * Attestation reason codes (meta-only, no device identifiers)
 */
object AttestationReasonCodes {
    const val ATTESTATION_OK = "ATTESTATION_OK"
    const val ATTESTATION_UNAVAILABLE = "ATTESTATION_UNAVAILABLE"
    const val ATTESTATION_INVALID = "ATTESTATION_INVALID"
    const val ATTESTATION_ERROR = "ATTESTATION_ERROR"
}

