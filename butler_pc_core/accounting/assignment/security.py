"""Tenant-scoped match tokens and tamper-evident checkpoint keys."""

from __future__ import annotations

import base64
import hashlib
import hmac
import os
import platform
import secrets
import subprocess
import unicodedata
from dataclasses import dataclass, field
from typing import Protocol

from .domain import AssignmentError


MATCH_CONTEXT = b"butler/accounting/vendor-match/v1"
CHECKPOINT_CONTEXT = b"butler/accounting/event-checkpoint/v1"
CURSOR_CONTEXT = b"butler/accounting/review-cursor/v1"
NORMALIZATION_VERSION = "vendor_descriptor_nfkc_ws_casefold_v1"


class SecureKeyStore(Protocol):
    def root_key(self) -> tuple[str, bytes]: ...


@dataclass(slots=True)
class MemoryKeyStore:
    """Tests only. Production wiring rejects this class."""

    key: bytes = field(default_factory=lambda: secrets.token_bytes(32))
    key_id: str = "test-memory-key-v1"

    def root_key(self) -> tuple[str, bytes]:
        return self.key_id, self.key


@dataclass(slots=True)
class MacOSKeychainStore:
    service: str = "com.butler.accounting.vendor-match.v1"
    account: str = "device-root"

    def root_key(self) -> tuple[str, bytes]:
        if platform.system() != "Darwin":
            raise AssignmentError("SECURE_KEY_UNAVAILABLE", 503, "The platform secure key store is unavailable.")
        try:
            found = subprocess.run(
                ["/usr/bin/security", "find-generic-password", "-a", self.account, "-s", self.service, "-w"],
                check=False,
                capture_output=True,
                timeout=5,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            raise AssignmentError("SECURE_KEY_UNAVAILABLE", 503, "The platform secure key store is unavailable.") from exc
        if found.returncode == 0:
            try:
                key = base64.urlsafe_b64decode(found.stdout.strip())
            except Exception as exc:
                raise AssignmentError("SECURE_KEY_UNAVAILABLE", 503, "The stored key is invalid.") from exc
            if len(key) != 32:
                raise AssignmentError("SECURE_KEY_UNAVAILABLE", 503, "The stored key is invalid.")
            return "macos-keychain-v1", key

        key = secrets.token_bytes(32)
        encoded = base64.urlsafe_b64encode(key) + b"\n"
        # Supplying -w without a value makes security read the secret from stdin,
        # keeping key bytes out of argv, logs, the repository, and the database.
        try:
            added = subprocess.run(
                [
                    "/usr/bin/security",
                    "add-generic-password",
                    "-U",
                    "-a",
                    self.account,
                    "-s",
                    self.service,
                    "-w",
                ],
                input=encoded,
                check=False,
                capture_output=True,
                timeout=10,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            raise AssignmentError("SECURE_KEY_UNAVAILABLE", 503, "The platform secure key store is unavailable.") from exc
        if added.returncode != 0:
            raise AssignmentError("SECURE_KEY_UNAVAILABLE", 503, "The platform secure key store rejected key creation.")
        return "macos-keychain-v1", key


def normalize_descriptor(value: str) -> str:
    if not isinstance(value, str):
        raise AssignmentError("CANONICAL_TRANSACTION_INVALID", 422, "Descriptor is invalid.")
    normalized = " ".join(unicodedata.normalize("NFKC", value).strip().split()).casefold()
    if not normalized or len(normalized) > 500:
        raise AssignmentError("CANONICAL_TRANSACTION_INVALID", 422, "Descriptor is invalid.")
    return normalized


def _field(value: str) -> bytes:
    raw = value.encode("utf-8")
    return len(raw).to_bytes(4, "big") + raw


@dataclass(slots=True)
class TokenService:
    key_store: SecureKeyStore

    def _tenant_key(self, tenant_id: str, context: bytes) -> tuple[str, bytes]:
        key_id, root = self.key_store.root_key()
        if len(root) < 32:
            raise AssignmentError("SECURE_KEY_UNAVAILABLE", 503, "The secure root key is invalid.")
        return key_id, hmac.new(root, context + _field(tenant_id), hashlib.sha256).digest()

    def vendor_token(self, tenant_id: str, adapter_family: str, descriptor: str) -> tuple[str, str]:
        key_id, tenant_key = self._tenant_key(tenant_id, MATCH_CONTEXT)
        canonical = normalize_descriptor(descriptor)
        body = (
            _field(tenant_id)
            + _field(adapter_family)
            + _field(NORMALIZATION_VERSION)
            + _field(canonical)
        )
        return key_id, hmac.new(tenant_key, body, hashlib.sha256).hexdigest()

    def checkpoint_mac(self, tenant_id: str, event_hash: str) -> str:
        _, key = self._tenant_key(tenant_id, CHECKPOINT_CONTEXT)
        return hmac.new(key, event_hash.encode("ascii"), hashlib.sha256).hexdigest()

    def cursor_mac(self, tenant_id: str, payload: bytes) -> bytes:
        _, key = self._tenant_key(tenant_id, CURSOR_CONTEXT)
        return hmac.new(key, payload, hashlib.sha256).digest()

    def self_test(self, tenant_id: str) -> str:
        key_id, key = self._tenant_key(tenant_id, CHECKPOINT_CONTEXT)
        probe = hmac.new(key, b"butler-accounting-keystore-self-test", hashlib.sha256).digest()
        if len(probe) != 32:
            raise AssignmentError("SECURE_KEY_UNAVAILABLE", 503, "The secure key self-test failed.")
        return key_id

    @staticmethod
    def idempotency_digest(value: str) -> str:
        return hashlib.sha256(value.encode("utf-8")).hexdigest()
