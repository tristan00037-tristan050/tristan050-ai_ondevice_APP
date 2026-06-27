"""Buffer-first stream helpers.

The public SSE stream must not receive model tokens until the final output guard
has evaluated the whole response. This helper makes that invariant explicit and
unit-testable.
"""

from __future__ import annotations

import re
from collections.abc import Iterable

from .guards import SAFE_FIXED_TEXT, GuardAction, GuardContext, GuardVerdict, SafeChatGuard


_THINK_BLOCK_RE = re.compile(r"<think>.*?</think>", re.IGNORECASE | re.DOTALL)
_UNCLOSED_THINK_RE = re.compile(r"<think>.*$", re.IGNORECASE | re.DOTALL)


def strip_think_blocks(text: str) -> str:
    cleaned = _THINK_BLOCK_RE.sub("", text or "")
    cleaned = _UNCLOSED_THINK_RE.sub("", cleaned)
    return cleaned.strip()


def strip_leading_think_blocks(tokens: Iterable[str]) -> str:
    return strip_think_blocks("".join(str(token) for token in tokens))


def guard_buffered_tokens(
    tokens: Iterable[str],
    *,
    guard: SafeChatGuard | None = None,
    context: GuardContext | None = None,
) -> tuple[str | None, GuardVerdict]:
    raw_text = "".join(str(token) for token in tokens)
    text = strip_think_blocks(raw_text)
    if not text:
        verdict = GuardVerdict(GuardAction.REPLACE, "EMPTY_AFTER_THINK_STRIP", SAFE_FIXED_TEXT)
        return verdict.allowed_text, verdict
    verdict = (guard or SafeChatGuard()).evaluate(text, context)
    if verdict.action == GuardAction.ALLOW:
        return text, verdict
    if verdict.action == GuardAction.REPLACE:
        return verdict.allowed_text, verdict
    return None, verdict
