"""Exact-only compiler for a user-provided account column."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Any

from butler_pc_core.accounting.assignment.domain import AssignmentError
from butler_pc_core.accounting.assignment.registry import RegistryEntry, RegistrySnapshot


DEFAULT_ALIASES = frozenset({"account_id", "account_code", "계정과목", "계정코드", "계정명"})


def normalize_header(value: object) -> str:
    return re.sub(r"\s+", "", unicodedata.normalize("NFKC", str(value))).casefold()


@dataclass(frozen=True, slots=True)
class AccountColumnResolution:
    selected_column: str | None
    ambiguous_columns: tuple[str, ...]


def resolve_account_column(
    columns: list[object],
    *,
    selected_column: str | None = None,
    aliases: frozenset[str] = DEFAULT_ALIASES,
) -> AccountColumnResolution:
    alias_keys = {normalize_header(item) for item in aliases}
    candidates = tuple(str(column) for column in columns if normalize_header(column) in alias_keys)
    if selected_column is not None:
        exact = [column for column in candidates if column == selected_column]
        if len(exact) != 1:
            raise AssignmentError("SOURCE_ACCOUNT_AMBIGUOUS", 422, "The selected account column is invalid.")
        return AccountColumnResolution(exact[0], ())
    if len(candidates) > 1:
        return AccountColumnResolution(None, candidates)
    return AccountColumnResolution(candidates[0] if candidates else None, ())


def resolve_account_cell(value: Any, registry: RegistrySnapshot) -> RegistryEntry | None:
    # Formula/error cells and non-scalar values never become assignments.
    if value is None or isinstance(value, (list, dict, tuple, set)):
        return None
    if isinstance(value, str) and value.lstrip().startswith("="):
        return None
    return registry.resolve_exact(value)
