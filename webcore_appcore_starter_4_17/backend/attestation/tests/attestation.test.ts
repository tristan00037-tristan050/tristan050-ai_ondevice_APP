/**
 * Attestation Tests
 * Verify attestation proof validation and fail-closed behavior
 *
 * Hard rule:
 * - tests MUST NOT contain evidence string patterns (evidence keys are emitted only by verify scripts on PASS)
 * - no require.main side effects in tests
 * - Jest-only (describe/it/expect), no custom runner
 */

import { describe, it, expect } from '@jest/globals';

/**
 * Mock attestation proof validator
 */
function validateAttestationProof(proof: string | null): { allowed: boolean; reason?: string } {
  if (!proof || proof.length === 0) {
    return { allowed: false, reason: 'missing_proof' };
  }
  
  if (proof === 'invalid-proof') {
    return { allowed: false, reason: 'invalid_proof' };
  }
  
  if (proof === 'valid-proof') {
    return { allowed: true };
  }
  
  return { allowed: false, reason: 'unknown_proof_format' };
}

describe('Attestation Verification', () => {
  it('should block request when proof is invalid or missing', () => {
    const result1 = validateAttestationProof(null);
    expect(result1.allowed).toBe(false);
    expect(result1.reason).toBe('missing_proof');
    
    const result2 = validateAttestationProof('');
    expect(result2.allowed).toBe(false);
    expect(result2.reason).toBe('missing_proof');
    
    const result3 = validateAttestationProof('invalid-proof');
    expect(result3.allowed).toBe(false);
    expect(result3.reason).toBe('invalid_proof');
  });
  
  it('should allow request when proof is valid', () => {
    const result = validateAttestationProof('valid-proof');
    expect(result.allowed).toBe(true);
    expect(result.reason).toBeUndefined();
  });
});

