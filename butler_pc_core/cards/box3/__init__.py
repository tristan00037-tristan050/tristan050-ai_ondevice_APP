"""Box 3 draft-from-reference contract package.

This package intentionally ships as contract-only unless all helper assets have
full 64-character SHA-256 values and interface inventory evidence.
"""

from .draft_service import BOX3_DRAFT_ENDPOINT, draft_from_current_contract
from .pipeline import run_box3_pipeline

__all__ = ["BOX3_DRAFT_ENDPOINT", "draft_from_current_contract", "run_box3_pipeline"]

