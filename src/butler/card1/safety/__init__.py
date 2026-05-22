"""Card 1 safety hardening entrypoint.

Card 1 = request core extraction. This package adds four fail-closed safety
controls: adapter SHA verification, allowlist validation, six invariants, and
rollback evidence generation.
"""

from .adapter_sha_verifier import AdapterShaVerification, verify_adapter_sha256
from .allowlist import AllowlistDecision, validate_card1_output
from .invariants import InvariantReport, validate_six_invariants
from .rollback import RollbackEvidence, build_rollback_evidence

__all__ = [
    "AdapterShaVerification",
    "verify_adapter_sha256",
    "AllowlistDecision",
    "validate_card1_output",
    "InvariantReport",
    "validate_six_invariants",
    "RollbackEvidence",
    "build_rollback_evidence",
]
