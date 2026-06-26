"""Buffer-first stream helpers.

The public SSE stream must not receive model tokens until the final output guard
has evaluated the whole response. This helper makes that invariant explicit and
unit-testable.
"""

from __future__ import annotations

from collections.abc import Iterable

from .guards import GuardAction, GuardContext, GuardVerdict, SafeChatGuard


def strip_leading_think_blocks(tokens: Iterable[str]) -> str:
    state = "before"
    output: list[str] = []
    for token in tokens:
        if state == "before":
            if "<think>" in token:
                pre, _sep, rest = token.partition("<think>")
                if pre:
                    output.append(pre)
                state = "in_think"
                if "</think>" in rest:
                    _ignored, _end, post = rest.partition("</think>")
                    if post:
                        output.append(post)
                    state = "after"
                continue
            state = "after"

        if state == "in_think":
            if "</think>" in token:
                _ignored, _end, post = token.partition("</think>")
                if post:
                    output.append(post)
                state = "after"
            continue

        output.append(token)
    return "".join(output)


def guard_buffered_tokens(
    tokens: Iterable[str],
    *,
    guard: SafeChatGuard | None = None,
    context: GuardContext | None = None,
) -> tuple[str | None, GuardVerdict]:
    text = strip_leading_think_blocks(tokens).strip()
    verdict = (guard or SafeChatGuard()).evaluate(text, context)
    if verdict.action == GuardAction.ALLOW:
        return text, verdict
    if verdict.action == GuardAction.REPLACE:
        return verdict.allowed_text, verdict
    return None, verdict
