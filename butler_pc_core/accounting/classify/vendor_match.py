"""Tenant-scoped exact vendor tokens for user-rule suggestions.

The algorithm never receives or stores a root secret.  A platform keystore
handle performs tenant/context key derivation and HMAC-SHA-256.  Returned tokens
are internal storage keys and are redacted from representations.
"""

from __future__ import annotations

import base64
import hmac
import re
import unicodedata
from dataclasses import dataclass, field
from typing import Protocol, Sequence


VENDOR_MATCH_CONTEXT = b"butler/accounting/vendor-match/v1"
VENDOR_NORMALIZATION_VERSION = "nfkc-ws-latin-casefold-v1"
_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,79}$")
_TOKEN_RE = re.compile(r"^tok_[A-Za-z0-9_-]{43}$")
_WHITESPACE_RE = re.compile(r"\s+")
_MAX_DESCRIPTOR_BYTES = 1_024
_MAX_KEYS = 3


class VendorMatchContractError(ValueError):
    """Vendor normalization, key service, or token metadata is invalid."""


class VendorMatchKeyHandle(Protocol):
    """Platform-owned secure keystore handle.

    The implementation must derive a key scoped to ``tenant_id`` and
    ``context`` inside the keystore, then return HMAC-SHA-256(payload).  It must
    not expose key bytes to this module.
    """

    @property
    def key_id(self) -> str: ...

    def tenant_context_hmac_sha256(
        self,
        *,
        tenant_id: str,
        context: bytes,
        payload: bytes,
    ) -> bytes: ...


def _require_id(value: str, name: str) -> None:
    if not isinstance(value, str) or not _ID_RE.fullmatch(value):
        raise VendorMatchContractError(f"{name}_INVALID")


def _latin_casefold(value: str) -> str:
    folded: list[str] = []
    for character in value:
        name = unicodedata.name(character, "")
        folded.append(character.casefold() if "LATIN" in name else character)
    return "".join(folded)


def normalize_vendor_descriptor(value: str) -> str:
    """Apply only the v2.1-approved non-destructive normalization."""

    if not isinstance(value, str):
        raise VendorMatchContractError("VENDOR_DESCRIPTOR_NOT_TEXT")
    normalized = unicodedata.normalize("NFKC", value)
    if any(
        unicodedata.category(character) in {"Cc", "Cf"} and not character.isspace()
        for character in normalized
    ):
        raise VendorMatchContractError("VENDOR_DESCRIPTOR_CONTROL_CHARACTER")
    normalized = _WHITESPACE_RE.sub(" ", normalized).strip()
    normalized = _latin_casefold(normalized)
    if not normalized:
        raise VendorMatchContractError("VENDOR_DESCRIPTOR_EMPTY")
    if len(normalized.encode("utf-8")) > _MAX_DESCRIPTOR_BYTES:
        raise VendorMatchContractError("VENDOR_DESCRIPTOR_TOO_LARGE")
    return normalized


def _frame(value: str, name: str) -> bytes:
    if not isinstance(value, str) or not value:
        raise VendorMatchContractError(f"{name}_INVALID")
    encoded = value.encode("utf-8")
    if len(encoded) > 65_535:
        raise VendorMatchContractError(f"{name}_TOO_LARGE")
    return len(encoded).to_bytes(4, "big") + encoded


def _payload(
    *,
    tenant_id: str,
    adapter_family: str,
    descriptor_schema_version: str,
    canonical_descriptor: str,
) -> bytes:
    _require_id(tenant_id, "TENANT_ID")
    _require_id(adapter_family, "ADAPTER_FAMILY")
    _require_id(descriptor_schema_version, "DESCRIPTOR_SCHEMA_VERSION")
    return b"".join(
        (
            _frame(tenant_id, "TENANT_ID"),
            _frame(adapter_family, "ADAPTER_FAMILY"),
            _frame(descriptor_schema_version, "DESCRIPTOR_SCHEMA_VERSION"),
            _frame(canonical_descriptor, "CANONICAL_DESCRIPTOR"),
        )
    )


@dataclass(frozen=True, slots=True, eq=False)
class VendorMatchToken:
    key_id: str
    adapter_family: str
    descriptor_schema_version: str
    normalization_version: str
    _storage_value: str = field(repr=False)

    def __post_init__(self) -> None:
        for value, name in (
            (self.key_id, "MATCH_KEY_ID"),
            (self.adapter_family, "ADAPTER_FAMILY"),
            (self.descriptor_schema_version, "DESCRIPTOR_SCHEMA_VERSION"),
            (self.normalization_version, "NORMALIZATION_VERSION"),
        ):
            _require_id(value, name)
        if not isinstance(self._storage_value, str) or not _TOKEN_RE.fullmatch(
            self._storage_value
        ):
            raise VendorMatchContractError("VENDOR_MATCH_TOKEN_INVALID")

    def storage_value(self) -> str:
        """Explicit internal-store access; never include this value in logs or API output."""

        return self._storage_value

    def matches_storage_value(self, candidate: str) -> bool:
        return isinstance(candidate, str) and hmac.compare_digest(
            self._storage_value, candidate
        )


@dataclass(frozen=True, slots=True)
class VendorMatchTokenSet:
    write_token: VendorMatchToken
    read_tokens: tuple[VendorMatchToken, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.write_token, VendorMatchToken):
            raise VendorMatchContractError("WRITE_TOKEN_INVALID")
        if (
            not isinstance(self.read_tokens, tuple)
            or not self.read_tokens
            or len(self.read_tokens) > _MAX_KEYS
            or any(
                not isinstance(token, VendorMatchToken) for token in self.read_tokens
            )
        ):
            raise VendorMatchContractError("READ_TOKENS_INVALID")
        key_ids = [token.key_id for token in self.read_tokens]
        if len(key_ids) != len(set(key_ids)):
            raise VendorMatchContractError("DUPLICATE_MATCH_KEY_ID")
        if self.read_tokens[0] is not self.write_token:
            raise VendorMatchContractError("ACTIVE_WRITE_TOKEN_NOT_FIRST_READ_TOKEN")
        metadata = {
            (
                token.adapter_family,
                token.descriptor_schema_version,
                token.normalization_version,
            )
            for token in self.read_tokens
        }
        if len(metadata) != 1:
            raise VendorMatchContractError("ROTATION_TOKEN_METADATA_MISMATCH")


def derive_vendor_match_token(
    canonical_descriptor: str,
    *,
    tenant_id: str,
    adapter_family: str,
    descriptor_schema_version: str,
    key_handle: VendorMatchKeyHandle,
) -> VendorMatchToken:
    """Derive one internal exact-match token through a secure key handle."""

    normalized = normalize_vendor_descriptor(canonical_descriptor)
    try:
        key_id = key_handle.key_id
    except Exception as exc:
        raise VendorMatchContractError("SECURE_KEY_UNAVAILABLE") from exc
    _require_id(key_id, "MATCH_KEY_ID")
    message = _payload(
        tenant_id=tenant_id,
        adapter_family=adapter_family,
        descriptor_schema_version=descriptor_schema_version,
        canonical_descriptor=normalized,
    )
    try:
        digest = key_handle.tenant_context_hmac_sha256(
            tenant_id=tenant_id,
            context=VENDOR_MATCH_CONTEXT,
            payload=message,
        )
    except VendorMatchContractError:
        raise
    except Exception as exc:
        raise VendorMatchContractError("SECURE_KEY_UNAVAILABLE") from exc
    if not isinstance(digest, bytes) or len(digest) != 32:
        raise VendorMatchContractError("SECURE_KEY_INVALID_HMAC_RESULT")
    encoded = base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")
    return VendorMatchToken(
        key_id=key_id,
        adapter_family=adapter_family,
        descriptor_schema_version=descriptor_schema_version,
        normalization_version=VENDOR_NORMALIZATION_VERSION,
        _storage_value=f"tok_{encoded}",
    )


def derive_vendor_match_token_set(
    canonical_descriptor: str,
    *,
    tenant_id: str,
    adapter_family: str,
    descriptor_schema_version: str,
    active_key: VendorMatchKeyHandle,
    retiring_keys: Sequence[VendorMatchKeyHandle] = (),
) -> VendorMatchTokenSet:
    """Create a dual-read/new-write set for bounded key rotation."""

    handles = (active_key, *tuple(retiring_keys))
    if not 1 <= len(handles) <= _MAX_KEYS:
        raise VendorMatchContractError("MATCH_KEY_RING_SIZE_INVALID")
    try:
        key_ids = [handle.key_id for handle in handles]
    except Exception as exc:
        raise VendorMatchContractError("SECURE_KEY_UNAVAILABLE") from exc
    if len(key_ids) != len(set(key_ids)):
        raise VendorMatchContractError("DUPLICATE_MATCH_KEY_ID")
    tokens = tuple(
        derive_vendor_match_token(
            canonical_descriptor,
            tenant_id=tenant_id,
            adapter_family=adapter_family,
            descriptor_schema_version=descriptor_schema_version,
            key_handle=handle,
        )
        for handle in handles
    )
    return VendorMatchTokenSet(write_token=tokens[0], read_tokens=tokens)
