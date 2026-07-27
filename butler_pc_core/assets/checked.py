from __future__ import annotations

from .errors import block

MAX_SAFE_OFFSET = (1 << 63) - 1


def checked_add(*values: int, limit: int = MAX_SAFE_OFFSET) -> int:
    total = 0
    for value in values:
        if type(value) is not int or value < 0:
            raise block("BLOCK_FORMAT_INVALID")
        if value > limit - total:
            raise block("INTEGER_OVERFLOW")
        total += value
    return total


def checked_mul(*values: int, limit: int = MAX_SAFE_OFFSET) -> int:
    total = 1
    for value in values:
        if type(value) is not int or value < 0:
            raise block("BLOCK_FORMAT_INVALID")
        if value and total > limit // value:
            raise block("INTEGER_OVERFLOW")
        total *= value
    return total
