"""Butler Helper1 v2 canonical on-device RAG package.

The package is deliberately fail closed.  Importing it never probes user
folders, provisions keys, loads models, or creates an index.
"""

from .contracts import (
    AnswerKind,
    AnswerResult,
    Citation,
    EncoderIdentity,
    GroundingPolicy,
    Helper1ContractError,
    IndexManifest,
    RetrievedChunk,
)

__all__ = [
    "AnswerKind",
    "AnswerResult",
    "Citation",
    "EncoderIdentity",
    "GroundingPolicy",
    "Helper1ContractError",
    "IndexManifest",
    "RetrievedChunk",
]
