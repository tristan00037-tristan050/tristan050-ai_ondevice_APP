"""Box 3 draft-from-reference contract package.

This package intentionally ships as contract-only unless all helper assets have
full 64-character SHA-256 values and interface inventory evidence.
"""

from .draft_service import BOX3_DRAFT_ENDPOINT, draft_from_current_contract
from .pipeline import run_box3_pipeline
from .real_contract import Box3RealRuntimeEnvelope
from .real_pipeline import run_box3_real_followup

__all__ = [
    "BOX3_DRAFT_ENDPOINT",
    "Box3RealRuntimeEnvelope",
    "draft_from_current_contract",
    "run_box3_pipeline",
    "run_box3_real_followup",
]
