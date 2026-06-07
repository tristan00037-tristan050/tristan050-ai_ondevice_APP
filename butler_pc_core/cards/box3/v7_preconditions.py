from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable

from .v7_fail_class import BLOCK_PRECONDITION_PR785_NOT_MERGED, BLOCK_GROUNDING_OR_JSON_SUPPRESSION_DRIFT
from .v7_security import sha256_text

REQUIRED_PR785_TOKENS = (
    "OUTPUT_FORMAT_STRICT",
    "본문",
    "[문서에 근거 없음]",
    "snippet",
)

@dataclass(frozen=True)
class PreconditionVerdict:
    passed: bool
    fail_class: str | None
    missing_tokens: list[str]
    source_digest: str | None

    def to_dict(self) -> dict:
        return asdict(self)


def verify_pr785_precondition(grounded_prompt_path: Path | None = None, *, allow_absorbed: bool = True) -> PreconditionVerdict:
    path = grounded_prompt_path or Path("butler_pc_core/cards/box3/grounded_prompt.py")
    if not path.exists():
        return PreconditionVerdict(False, BLOCK_PRECONDITION_PR785_NOT_MERGED, ["grounded_prompt.py"], None)
    text = path.read_text(encoding="utf-8")
    required = ["OUTPUT_FORMAT_STRICT", "본문", "[문서에 근거 없음]"]
    missing = [token for token in required if token not in text]
    # Absorbed package can include strict prompt even when PR #785 is not merged.
    if missing:
        return PreconditionVerdict(False, BLOCK_PRECONDITION_PR785_NOT_MERGED, missing, sha256_text(text))
    # Strict prompt should not reintroduce raw snippet persistence helpers.
    forbidden_persist_markers = ["reference_snippets", "draft_snippet", "drafting_request_snippet"]
    drift = [token for token in forbidden_persist_markers if token in text]
    if drift:
        return PreconditionVerdict(False, BLOCK_GROUNDING_OR_JSON_SUPPRESSION_DRIFT, drift, sha256_text(text))
    return PreconditionVerdict(True, None, [], sha256_text(text))
