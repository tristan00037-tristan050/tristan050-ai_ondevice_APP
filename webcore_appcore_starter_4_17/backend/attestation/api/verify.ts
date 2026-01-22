/**
 * Attestation Verification API Router
 * HTTP endpoint for attestation proof verification
 */

import express, { Request, Response } from 'express';
import { validateAttestationProof } from '../verify/validator';
import { attestationStore } from '../store/memory';

const router = express.Router();

interface VerifyRequest {
  tenant_id: string;
  proof: string | null;
}

/**
 * POST /api/v1/attestation/verify
 * Verify attestation proof and record decision
 */
router.post('/verify', async (req: Request, res: Response) => {
  try {
    const body = req.body as VerifyRequest;

    if (!body.tenant_id) {
      return res.status(400).json({
        allowed: false,
        reason_code: 'ATTEST_MISSING_TENANT_ID',
      });
    }

    // Validate proof
    const validation = validateAttestationProof(body.proof);

    // Record decision
    attestationStore.record(
      body.tenant_id,
      validation.allowed,
      validation.allowed ? undefined : validation.reason_code
    );

    if (validation.allowed) {
      return res.status(200).json({
        allowed: true,
      });
    } else {
      return res.status(403).json({
        allowed: false,
        reason_code: validation.reason_code,
      });
    }
  } catch (error) {
    console.error('[attestation] Verify error:', error);
    return res.status(500).json({
      allowed: false,
      reason_code: 'ATTEST_INTERNAL_ERROR',
    });
  }
});

export default router;

