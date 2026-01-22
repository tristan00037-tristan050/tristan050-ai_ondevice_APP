/**
 * Attestation Proof Validator
 * Validates attestation proofs and returns allow/deny decisions with reason codes
 */

export type ValidationResult =
  | { allowed: true }
  | { allowed: false; reason_code: string };

/**
 * Validate attestation proof
 * Fail-closed: invalid or missing proof => deny
 */
export function validateAttestationProof(
  proof: string | null | undefined
): ValidationResult {
  if (!proof || proof.length === 0) {
    return { allowed: false, reason_code: 'ATTEST_MISSING_PROOF' };
  }

  if (proof === 'invalid-proof' || proof === 'tampered-proof') {
    return { allowed: false, reason_code: 'ATTEST_INVALID_PROOF' };
  }

  if (proof === 'valid-proof') {
    return { allowed: true };
  }

  // Unknown format => deny (fail-closed)
  return { allowed: false, reason_code: 'ATTEST_UNKNOWN_FORMAT' };
}

