/**
 * Attestation Client Tests
 * Verify attestation token generation and attachment
 */

package com.webcore.mobile.tests

import com.webcore.mobile.attestation.AttestationClient
import com.webcore.mobile.attestation.AttestationProvider
import com.webcore.mobile.attestation.AttestationResult
import com.webcore.mobile.attestation.AttestationReasonCodes
import com.webcore.mobile.update.config.ConfigFetcher
import com.webcore.mobile.update.model.ModelFetcher
import kotlinx.coroutines.runBlocking

// Simple test runner
fun test(name: String, fn: () -> Unit) {
    try {
        fn()
        println("PASS: $name")
    } catch (e: Exception) {
        println("FAIL: $name: ${e.message}")
        throw e
    }
}

fun expect(actual: Any?) {
    return object {
        fun toBe(expected: Any?) {
            if (actual != expected) {
                throw AssertionError("Expected $expected, got $actual")
            }
        }
        fun toBeNull() {
            if (actual != null) {
                throw AssertionError("Expected null, got $actual")
            }
        }
        fun notToBeNull() {
            if (actual == null) {
                throw AssertionError("Expected not null, got null")
            }
        }
        fun toBeTrue() {
            if (actual != true) {
                throw AssertionError("Expected true, got $actual")
            }
        }
        fun toBeFalse() {
            if (actual != false) {
                throw AssertionError("Expected false, got $actual")
            }
        }
    }
}

/**
 * Mock attestation provider (success)
 */
class MockSuccessAttestationProvider : AttestationProvider {
    override suspend fun obtainToken(): AttestationResult {
        return AttestationResult.Success("mock-attestation-token-12345")
    }
}

/**
 * Mock attestation provider (failure)
 */
class MockFailureAttestationProvider : AttestationProvider {
    override suspend fun obtainToken(): AttestationResult {
        return AttestationResult.Failure(AttestationReasonCodes.ATTESTATION_UNAVAILABLE)
    }
}

fun main() {
    runBlocking {
        test("should attach attestation token to request when provider succeeds") {
            val provider = MockSuccessAttestationProvider()
            val client = AttestationClient(provider)
            
            val (token, reason) = client.getTokenForRequest()
            expect(token).notToBeNull()
            expect(token).toBe("mock-attestation-token-12345")
            expect(reason).toBeNull()
        }
        
        test("should block request when attestation provider fails") {
            val provider = MockFailureAttestationProvider()
            val client = AttestationClient(provider)
            
            val (token, reason) = client.getTokenForRequest()
            expect(token).toBeNull()
            expect(reason).notToBeNull()
            expect(reason).toBe(AttestationReasonCodes.ATTESTATION_UNAVAILABLE)
        }
        
        test("should block config fetch when attestation fails") {
            val provider = MockFailureAttestationProvider()
            val client = AttestationClient(provider)
            val fetcher = ConfigFetcher("https://api.example.com", client)
            
            val isAllowed = fetcher.isFetchAllowed()
            expect(isAllowed).toBeFalse()
            
            val result = fetcher.fetch("config.json")
            when (result) {
                is com.webcore.mobile.update.config.ConfigFetchResult.Success -> {
                    throw AssertionError("Expected failure, got success")
                }
                is com.webcore.mobile.update.config.ConfigFetchResult.Failure -> {
                    expect(result.reasonCode).toBe(AttestationReasonCodes.ATTESTATION_UNAVAILABLE)
                }
            }
        }
        
        test("should block model fetch when attestation fails") {
            val provider = MockFailureAttestationProvider()
            val client = AttestationClient(provider)
            val fetcher = ModelFetcher("https://api.example.com", client)
            
            val isAllowed = fetcher.isFetchAllowed()
            expect(isAllowed).toBeFalse()
            
            val result = fetcher.fetch("model.onnx")
            when (result) {
                is com.webcore.mobile.update.model.ModelFetchResult.Success -> {
                    throw AssertionError("Expected failure, got success")
                }
                is com.webcore.mobile.update.model.ModelFetchResult.Failure -> {
                    expect(result.reasonCode).toBe(AttestationReasonCodes.ATTESTATION_UNAVAILABLE)
                }
            }
        }
        
        test("should allow fetch when no attestation client provided") {
            val fetcher = ConfigFetcher("https://api.example.com", null)
            val isAllowed = fetcher.isFetchAllowed()
            expect(isAllowed).toBeTrue()
        }
    }
    
    // Output-based proof
    println("ATTEST_CLIENT_SEND_OK=1")
    println("ATTEST_BLOCK_ENFORCED_OK=1")
}

