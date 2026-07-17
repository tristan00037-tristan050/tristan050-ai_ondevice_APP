"""Strict account-column compilation for registered accounting imports.

This module is product code used before learned-rule and legacy classification.
It deliberately performs no fuzzy matching and never persists raw cell values.
"""

from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Sequence


_DIGEST_RE = re.compile(r"^[0-9a-f]{64}$")
_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
_COORDINATE_RE = re.compile(r"^[A-Z]{1,3}[1-9][0-9]{0,6}$")
_WHITESPACE_RE = re.compile(r"\s+")
_FORMULA_PREFIXES = ("=", "+", "-", "@")
_MAX_CELL_BYTES = 512
_MAX_COLUMNS = 16_384
_MAX_REGISTRY_ENTRIES = 10_000


class AccountColumnContractError(ValueError):
    """Untrusted source data or a registry snapshot violated the contract."""


class SourceCellKind(StrEnum):
    TEXT = "TEXT"
    BLANK = "BLANK"
    NUMBER = "NUMBER"
    BOOLEAN = "BOOLEAN"
    FORMULA = "FORMULA"
    ERROR = "ERROR"


class HeaderResolutionStatus(StrEnum):
    NOT_FOUND = "NOT_FOUND"
    SELECTED = "SELECTED"
    SELECTION_REQUIRED = "SELECTION_REQUIRED"


class AccountColumnState(StrEnum):
    ABSENT = "ABSENT"
    SOURCE_DECLARED_VALID = "SOURCE_DECLARED_VALID"
    REVIEW_REQUIRED = "REVIEW_REQUIRED"


class AccountColumnReason(StrEnum):
    ACCOUNT_COLUMN_NOT_FOUND = "ACCOUNT_COLUMN_NOT_FOUND"
    ACCOUNT_COLUMN_EXACT_ALIAS = "ACCOUNT_COLUMN_EXACT_ALIAS"
    ACCOUNT_COLUMN_SELECTION_REQUIRED = "ACCOUNT_COLUMN_SELECTION_REQUIRED"
    SOURCE_ACCOUNT_EXACT_ID = "SOURCE_ACCOUNT_EXACT_ID"
    SOURCE_ACCOUNT_EXACT_CODE = "SOURCE_ACCOUNT_EXACT_CODE"
    SOURCE_ACCOUNT_EXACT_NAME = "SOURCE_ACCOUNT_EXACT_NAME"
    SOURCE_ACCOUNT_EMPTY = "SOURCE_ACCOUNT_EMPTY"
    SOURCE_ACCOUNT_NON_TEXT = "SOURCE_ACCOUNT_NON_TEXT"
    SOURCE_ACCOUNT_FORMULA_OR_ERROR = "SOURCE_ACCOUNT_FORMULA_OR_ERROR"
    SOURCE_ACCOUNT_UNKNOWN = "SOURCE_ACCOUNT_UNKNOWN"
    SOURCE_ACCOUNT_DUPLICATE_NAME = "SOURCE_ACCOUNT_DUPLICATE_NAME"
    SOURCE_ACCOUNT_NONASSIGNABLE = "SOURCE_ACCOUNT_NONASSIGNABLE"


def _require_digest(value: str, name: str) -> None:
    if not isinstance(value, str) or not _DIGEST_RE.fullmatch(value):
        raise AccountColumnContractError(f"{name}_INVALID")


def _require_identifier(value: str, name: str) -> None:
    if not isinstance(value, str) or not _ID_RE.fullmatch(value):
        raise AccountColumnContractError(f"{name}_INVALID")


def _latin_casefold(value: str) -> str:
    folded: list[str] = []
    for character in value:
        name = unicodedata.name(character, "")
        folded.append(character.casefold() if "LATIN" in name else character)
    return "".join(folded)


def normalize_account_label(value: str) -> str:
    """NFKC + trim/collapse whitespace + Latin-only casefold.

    Punctuation, digits, branch names, corporate suffixes, and non-Latin case are
    preserved.  This is intentionally narrower than fuzzy or semantic matching.
    """

    if not isinstance(value, str):
        raise AccountColumnContractError("ACCOUNT_LABEL_NOT_TEXT")
    normalized = unicodedata.normalize("NFKC", value)
    normalized = _WHITESPACE_RE.sub(" ", normalized).strip()
    return _latin_casefold(normalized)


def _stable_digest(value: Any) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


@dataclass(frozen=True, slots=True)
class SourceCell:
    """Ephemeral imported cell.  ``value`` is excluded from repr and receipts."""

    column_index: int
    coordinate: str
    kind: SourceCellKind
    value: str | None = field(default=None, repr=False)

    def __post_init__(self) -> None:
        if (
            isinstance(self.column_index, bool)
            or not isinstance(self.column_index, int)
            or not 0 <= self.column_index < _MAX_COLUMNS
        ):
            raise AccountColumnContractError("SOURCE_COLUMN_INDEX_INVALID")
        if not isinstance(self.coordinate, str) or not _COORDINATE_RE.fullmatch(
            self.coordinate
        ):
            raise AccountColumnContractError("SOURCE_CELL_COORDINATE_INVALID")
        if not isinstance(self.kind, SourceCellKind):
            raise AccountColumnContractError("SOURCE_CELL_KIND_INVALID")
        if self.kind is SourceCellKind.BLANK:
            if self.value not in (None, ""):
                raise AccountColumnContractError("BLANK_CELL_HAS_VALUE")
        elif not isinstance(self.value, str):
            raise AccountColumnContractError("SOURCE_CELL_VALUE_INVALID")
        if self.value is not None and len(self.value.encode("utf-8")) > _MAX_CELL_BYTES:
            raise AccountColumnContractError("SOURCE_CELL_TOO_LARGE")

    @property
    def raw_digest(self) -> str:
        payload = (
            self.kind.value.encode("ascii")
            + b"\x00"
            + (self.value or "").encode("utf-8")
        )
        return hashlib.sha256(payload).hexdigest()

    def exact_text(self) -> str | None:
        if self.kind is not SourceCellKind.TEXT or self.value is None:
            return None
        if any(
            unicodedata.category(character) in {"Cc", "Cf"} for character in self.value
        ):
            return None
        if self.value.lstrip().startswith(_FORMULA_PREFIXES):
            return None
        return self.value


@dataclass(frozen=True, slots=True)
class AccountAliasRegistry:
    locale: str
    version: str
    aliases: tuple[str, ...]
    digest: str = field(init=False)
    normalized_aliases: frozenset[str] = field(init=False, repr=False)

    def __post_init__(self) -> None:
        _require_identifier(self.version, "ALIAS_REGISTRY_VERSION")
        if not isinstance(self.locale, str) or not 2 <= len(self.locale) <= 32:
            raise AccountColumnContractError("ALIAS_REGISTRY_LOCALE_INVALID")
        if not isinstance(self.aliases, tuple) or not 1 <= len(self.aliases) <= 128:
            raise AccountColumnContractError("ALIAS_REGISTRY_ENTRIES_INVALID")
        normalized = tuple(normalize_account_label(alias) for alias in self.aliases)
        if any(not alias for alias in normalized):
            raise AccountColumnContractError("ALIAS_REGISTRY_EMPTY_ALIAS")
        if len(normalized) != len(set(normalized)):
            raise AccountColumnContractError("ALIAS_REGISTRY_DUPLICATE")
        object.__setattr__(self, "normalized_aliases", frozenset(normalized))
        object.__setattr__(
            self,
            "digest",
            _stable_digest(
                {
                    "schema_version": "butler.account_column_aliases.v1",
                    "locale": self.locale,
                    "version": self.version,
                    "aliases": sorted(normalized),
                }
            ),
        )


@dataclass(frozen=True, slots=True)
class AccountRegistryEntry:
    account_id: str
    account_code: str | None
    display_name: str
    assignable: bool
    disabled_reason: str | None = None

    def __post_init__(self) -> None:
        _require_identifier(self.account_id, "ACCOUNT_ID")
        if self.account_code is not None:
            if (
                not isinstance(self.account_code, str)
                or not 1 <= len(self.account_code) <= 64
                or any(
                    unicodedata.category(character) in {"Cc", "Cf"}
                    for character in self.account_code
                )
            ):
                raise AccountColumnContractError("ACCOUNT_CODE_INVALID")
        if not isinstance(self.display_name, str) or not normalize_account_label(
            self.display_name
        ):
            raise AccountColumnContractError("ACCOUNT_DISPLAY_NAME_INVALID")
        if not isinstance(self.assignable, bool):
            raise AccountColumnContractError("ACCOUNT_ASSIGNABLE_INVALID")
        if self.assignable and self.disabled_reason is not None:
            raise AccountColumnContractError("ASSIGNABLE_ACCOUNT_HAS_DISABLED_REASON")
        if not self.assignable and (
            not isinstance(self.disabled_reason, str) or not self.disabled_reason
        ):
            raise AccountColumnContractError("NONASSIGNABLE_ACCOUNT_REASON_REQUIRED")


@dataclass(frozen=True, slots=True)
class AccountRegistrySnapshot:
    registry_digest: str
    overlay_digest: str
    locale: str
    entries: tuple[AccountRegistryEntry, ...]

    def __post_init__(self) -> None:
        _require_digest(self.registry_digest, "REGISTRY_DIGEST")
        _require_digest(self.overlay_digest, "OVERLAY_DIGEST")
        if not isinstance(self.locale, str) or not 2 <= len(self.locale) <= 32:
            raise AccountColumnContractError("REGISTRY_LOCALE_INVALID")
        if (
            not isinstance(self.entries, tuple)
            or not self.entries
            or len(self.entries) > _MAX_REGISTRY_ENTRIES
        ):
            raise AccountColumnContractError("REGISTRY_ENTRIES_INVALID")
        if any(not isinstance(entry, AccountRegistryEntry) for entry in self.entries):
            raise AccountColumnContractError("REGISTRY_ENTRY_INVALID")
        account_ids = [entry.account_id for entry in self.entries]
        if len(account_ids) != len(set(account_ids)):
            raise AccountColumnContractError("REGISTRY_DUPLICATE_ACCOUNT_ID")
        codes = [
            entry.account_code
            for entry in self.entries
            if entry.account_code is not None
        ]
        if len(codes) != len(set(codes)):
            raise AccountColumnContractError("REGISTRY_DUPLICATE_ACCOUNT_CODE")

    def require_assignable(self, account_id: str) -> AccountRegistryEntry:
        for entry in self.entries:
            if entry.account_id == account_id:
                if not entry.assignable:
                    raise AccountColumnContractError("SOURCE_ACCOUNT_NONASSIGNABLE")
                return entry
        raise AccountColumnContractError("SOURCE_ACCOUNT_UNKNOWN")


@dataclass(frozen=True, slots=True)
class HeaderResolution:
    status: HeaderResolutionStatus
    reason: AccountColumnReason
    candidate_columns: tuple[int, ...]
    selected_column: int | None = None
    header_coordinate: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.status, HeaderResolutionStatus) or not isinstance(
            self.reason, AccountColumnReason
        ):
            raise AccountColumnContractError("HEADER_RESOLUTION_ENUM_INVALID")
        if (
            not isinstance(self.candidate_columns, tuple)
            or any(
                isinstance(column, bool)
                or not isinstance(column, int)
                or not 0 <= column < _MAX_COLUMNS
                for column in self.candidate_columns
            )
            or len(self.candidate_columns) != len(set(self.candidate_columns))
        ):
            raise AccountColumnContractError("HEADER_CANDIDATES_INVALID")
        if self.status is HeaderResolutionStatus.SELECTED:
            if self.selected_column is None or self.header_coordinate is None:
                raise AccountColumnContractError("HEADER_SELECTION_INCOMPLETE")
            if self.selected_column not in self.candidate_columns:
                raise AccountColumnContractError("HEADER_SELECTION_NOT_CANDIDATE")
        elif self.selected_column is not None or self.header_coordinate is not None:
            raise AccountColumnContractError("UNSELECTED_HEADER_HAS_SELECTION")


@dataclass(frozen=True, slots=True)
class AccountColumnReceipt:
    source_file_digest: str
    sheet_id: str
    table_id: str | None
    header_cell_coordinate: str
    alias_registry_digest: str
    selected_column: int
    cell_raw_digest: str
    resolved_account_id: str | None
    registry_digest: str
    overlay_digest: str
    reason_code: AccountColumnReason
    schema_version: str = field(default="butler.account_column_receipt.v1", init=False)

    def __post_init__(self) -> None:
        for value, name in (
            (self.source_file_digest, "SOURCE_FILE_DIGEST"),
            (self.alias_registry_digest, "ALIAS_REGISTRY_DIGEST"),
            (self.cell_raw_digest, "CELL_RAW_DIGEST"),
            (self.registry_digest, "REGISTRY_DIGEST"),
            (self.overlay_digest, "OVERLAY_DIGEST"),
        ):
            _require_digest(value, name)
        _require_identifier(self.sheet_id, "SHEET_ID")
        if self.table_id is not None:
            _require_identifier(self.table_id, "TABLE_ID")
        if not isinstance(
            self.header_cell_coordinate, str
        ) or not _COORDINATE_RE.fullmatch(self.header_cell_coordinate):
            raise AccountColumnContractError("HEADER_CELL_COORDINATE_INVALID")
        if (
            isinstance(self.selected_column, bool)
            or not isinstance(self.selected_column, int)
            or not 0 <= self.selected_column < _MAX_COLUMNS
        ):
            raise AccountColumnContractError("SELECTED_COLUMN_INVALID")
        if self.resolved_account_id is not None:
            _require_identifier(self.resolved_account_id, "RESOLVED_ACCOUNT_ID")
        if not isinstance(self.reason_code, AccountColumnReason):
            raise AccountColumnContractError("ACCOUNT_COLUMN_REASON_INVALID")

    def to_mapping(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "source_file_digest": self.source_file_digest,
            "sheet_id": self.sheet_id,
            "table_id": self.table_id,
            "header_cell_coordinate": self.header_cell_coordinate,
            "alias_registry_digest": self.alias_registry_digest,
            "selected_column": self.selected_column,
            "cell_raw_digest": self.cell_raw_digest,
            "resolved_account_id": self.resolved_account_id,
            "registry_digest": self.registry_digest,
            "overlay_digest": self.overlay_digest,
            "reason_code": self.reason_code.value,
        }

    @property
    def digest(self) -> str:
        return _stable_digest(self.to_mapping())


@dataclass(frozen=True, slots=True)
class AccountColumnResolution:
    state: AccountColumnState
    reason: AccountColumnReason
    account_id: str | None = None
    receipt: AccountColumnReceipt | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.state, AccountColumnState) or not isinstance(
            self.reason, AccountColumnReason
        ):
            raise AccountColumnContractError("ACCOUNT_COLUMN_RESULT_ENUM_INVALID")
        if self.state is AccountColumnState.SOURCE_DECLARED_VALID:
            if self.account_id is None or self.receipt is None:
                raise AccountColumnContractError("VALID_SOURCE_ACCOUNT_INCOMPLETE")
            if self.receipt.resolved_account_id != self.account_id:
                raise AccountColumnContractError("SOURCE_ACCOUNT_RECEIPT_MISMATCH")
            if self.reason not in {
                AccountColumnReason.SOURCE_ACCOUNT_EXACT_ID,
                AccountColumnReason.SOURCE_ACCOUNT_EXACT_CODE,
                AccountColumnReason.SOURCE_ACCOUNT_EXACT_NAME,
            }:
                raise AccountColumnContractError("SOURCE_ACCOUNT_VALID_REASON_INVALID")
        else:
            if self.account_id is not None:
                raise AccountColumnContractError("UNRESOLVED_SOURCE_HAS_ACCOUNT")
            if (
                self.receipt is not None
                and self.receipt.resolved_account_id is not None
            ):
                raise AccountColumnContractError("UNRESOLVED_RECEIPT_HAS_ACCOUNT")
            if self.state is AccountColumnState.ABSENT and self.receipt is not None:
                raise AccountColumnContractError("ABSENT_COLUMN_HAS_RECEIPT")


class AccountColumnCompiler:
    """Compile exact source-account declarations against verified snapshots."""

    CONTRACT_VERSION = "butler.account_column_compiler.v2.1"

    def __init__(
        self,
        aliases: AccountAliasRegistry,
        registry: AccountRegistrySnapshot,
    ) -> None:
        if aliases.locale != registry.locale:
            raise AccountColumnContractError("ALIAS_REGISTRY_LOCALE_MISMATCH")
        self._aliases = aliases
        self._registry = registry
        self._by_id = {entry.account_id: entry for entry in registry.entries}
        self._by_code = {
            entry.account_code: entry
            for entry in registry.entries
            if entry.account_code is not None
        }
        by_name: dict[str, list[AccountRegistryEntry]] = {}
        for entry in registry.entries:
            by_name.setdefault(normalize_account_label(entry.display_name), []).append(
                entry
            )
        self._by_name = {key: tuple(values) for key, values in by_name.items()}

    def detect_header(
        self,
        headers: Sequence[SourceCell],
        *,
        selected_column: int | None = None,
    ) -> HeaderResolution:
        if len(headers) > _MAX_COLUMNS:
            raise AccountColumnContractError("HEADER_COLUMN_LIMIT_EXCEEDED")
        if any(not isinstance(cell, SourceCell) for cell in headers):
            raise AccountColumnContractError("HEADER_CELL_INVALID")
        indices = [cell.column_index for cell in headers]
        if len(indices) != len(set(indices)):
            raise AccountColumnContractError("DUPLICATE_HEADER_COLUMN_INDEX")
        candidates: list[SourceCell] = []
        for cell in headers:
            text = cell.exact_text()
            if (
                text is not None
                and normalize_account_label(text) in self._aliases.normalized_aliases
            ):
                candidates.append(cell)
        candidate_columns = tuple(cell.column_index for cell in candidates)
        if not candidates:
            if selected_column is not None:
                raise AccountColumnContractError("ACCOUNT_COLUMN_SELECTION_INVALID")
            return HeaderResolution(
                HeaderResolutionStatus.NOT_FOUND,
                AccountColumnReason.ACCOUNT_COLUMN_NOT_FOUND,
                (),
            )
        if selected_column is None and len(candidates) > 1:
            return HeaderResolution(
                HeaderResolutionStatus.SELECTION_REQUIRED,
                AccountColumnReason.ACCOUNT_COLUMN_SELECTION_REQUIRED,
                candidate_columns,
            )
        chosen = (
            candidates[0]
            if selected_column is None
            else next(
                (cell for cell in candidates if cell.column_index == selected_column),
                None,
            )
        )
        if chosen is None:
            raise AccountColumnContractError("ACCOUNT_COLUMN_SELECTION_INVALID")
        return HeaderResolution(
            HeaderResolutionStatus.SELECTED,
            AccountColumnReason.ACCOUNT_COLUMN_EXACT_ALIAS,
            candidate_columns,
            selected_column=chosen.column_index,
            header_coordinate=chosen.coordinate,
        )

    def resolve_cell(
        self,
        header: HeaderResolution,
        cell: SourceCell | None,
        *,
        source_file_digest: str,
        sheet_id: str,
        table_id: str | None = None,
    ) -> AccountColumnResolution:
        if not isinstance(header, HeaderResolution):
            raise AccountColumnContractError("HEADER_RESOLUTION_INVALID")
        if cell is not None and not isinstance(cell, SourceCell):
            raise AccountColumnContractError("ACCOUNT_CELL_INVALID")
        _require_digest(source_file_digest, "SOURCE_FILE_DIGEST")
        _require_identifier(sheet_id, "SHEET_ID")
        if table_id is not None:
            _require_identifier(table_id, "TABLE_ID")
        if header.status is HeaderResolutionStatus.NOT_FOUND:
            if cell is not None:
                raise AccountColumnContractError("CELL_WITHOUT_ACCOUNT_COLUMN")
            return AccountColumnResolution(
                AccountColumnState.ABSENT,
                AccountColumnReason.ACCOUNT_COLUMN_NOT_FOUND,
            )
        if header.status is HeaderResolutionStatus.SELECTION_REQUIRED:
            if cell is not None:
                raise AccountColumnContractError("CELL_BEFORE_ACCOUNT_COLUMN_SELECTION")
            return AccountColumnResolution(
                AccountColumnState.REVIEW_REQUIRED,
                AccountColumnReason.ACCOUNT_COLUMN_SELECTION_REQUIRED,
            )
        if cell is None or cell.column_index != header.selected_column:
            raise AccountColumnContractError("ACCOUNT_CELL_COLUMN_MISMATCH")

        reason: AccountColumnReason
        resolved: AccountRegistryEntry | None = None
        exact = cell.exact_text()
        if cell.kind is SourceCellKind.BLANK or cell.value == "":
            reason = AccountColumnReason.SOURCE_ACCOUNT_EMPTY
        elif cell.kind in {SourceCellKind.FORMULA, SourceCellKind.ERROR} or (
            cell.kind is SourceCellKind.TEXT
            and cell.value is not None
            and cell.value.lstrip().startswith(_FORMULA_PREFIXES)
        ):
            reason = AccountColumnReason.SOURCE_ACCOUNT_FORMULA_OR_ERROR
        elif exact is None:
            reason = AccountColumnReason.SOURCE_ACCOUNT_NON_TEXT
        elif exact in self._by_id:
            resolved = self._by_id[exact]
            reason = AccountColumnReason.SOURCE_ACCOUNT_EXACT_ID
        elif exact in self._by_code:
            resolved = self._by_code[exact]
            reason = AccountColumnReason.SOURCE_ACCOUNT_EXACT_CODE
        else:
            display_matches = self._by_name.get(normalize_account_label(exact), ())
            if len(display_matches) == 1:
                resolved = display_matches[0]
                reason = AccountColumnReason.SOURCE_ACCOUNT_EXACT_NAME
            elif len(display_matches) > 1:
                reason = AccountColumnReason.SOURCE_ACCOUNT_DUPLICATE_NAME
            else:
                reason = AccountColumnReason.SOURCE_ACCOUNT_UNKNOWN

        if resolved is not None and not resolved.assignable:
            resolved = None
            reason = AccountColumnReason.SOURCE_ACCOUNT_NONASSIGNABLE

        if header.header_coordinate is None or header.selected_column is None:
            raise AccountColumnContractError("HEADER_SELECTION_INCOMPLETE")
        receipt = AccountColumnReceipt(
            source_file_digest=source_file_digest,
            sheet_id=sheet_id,
            table_id=table_id,
            header_cell_coordinate=header.header_coordinate,
            alias_registry_digest=self._aliases.digest,
            selected_column=header.selected_column,
            cell_raw_digest=cell.raw_digest,
            resolved_account_id=resolved.account_id if resolved else None,
            registry_digest=self._registry.registry_digest,
            overlay_digest=self._registry.overlay_digest,
            reason_code=reason,
        )
        if resolved is None:
            return AccountColumnResolution(
                AccountColumnState.REVIEW_REQUIRED,
                reason,
                receipt=receipt,
            )
        return AccountColumnResolution(
            AccountColumnState.SOURCE_DECLARED_VALID,
            reason,
            account_id=resolved.account_id,
            receipt=receipt,
        )
