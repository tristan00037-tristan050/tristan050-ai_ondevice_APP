"""Box5 stage-3 shadow observation (observe-only).

The new Stage3Classifier runs alongside the existing classifier and its result is recorded for
Group A's 295-case comparison. It NEVER changes the product response, NEVER auto-consumes an
AUTO_PROPOSE, and JOURNAL_AUTO_POST_ALLOWED stays NO. No journal/ledger/report code lives here.
"""

from .record import Agreement, ShadowComparisonRecord, classify_agreement, digest_text
from .adapter import AtlinkShadowPort, build_canonical_transaction, transaction_key
from .runner import (
    run_shadow_over_rows,
    run_shadow_over_dataframe,
    rows_from_dataframe,
    shadow_one,
)

__all__ = [
    "Agreement",
    "ShadowComparisonRecord",
    "classify_agreement",
    "digest_text",
    "AtlinkShadowPort",
    "build_canonical_transaction",
    "transaction_key",
    "run_shadow_over_rows",
    "run_shadow_over_dataframe",
    "rows_from_dataframe",
    "shadow_one",
]
