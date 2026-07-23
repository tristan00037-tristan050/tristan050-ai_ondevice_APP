"""Tenant-scoped match tokens and tamper-evident checkpoint keys."""

from __future__ import annotations

import base64
import hashlib
import hmac
import platform
import re
import secrets
import subprocess
import unicodedata
from dataclasses import dataclass, field
from typing import Protocol

from butler_pc_core.accounting.classify.vendor_match import (
    VENDOR_NORMALIZATION_VERSION,
    VendorMatchContractError,
    normalize_vendor_descriptor,
)

from .domain import AssignmentError


MATCH_CONTEXT = b"butler/accounting/vendor-match/v1"
CHECKPOINT_CONTEXT = b"butler/accounting/event-checkpoint/v1"
CURSOR_CONTEXT = b"butler/accounting/review-cursor/v1"
A4_OWN_ACCOUNT_CONTEXT = b"BUTLER/A4/OWN_ACCOUNT/V3.1"
A4_REFERENCE_CONTEXT = b"butler/box5/a4/bank-reference/v1"
A4_ALIAS_CONTEXT = b"butler/box5/a4/counterparty-alias/v1"
A4_COUNTER_ACCOUNT_CONTEXT = b"butler/box5/a4/counterparty-account/v2"
A4_TXN_CONTEXT = b"butler/box5/a4/run-transaction/v1"
_A4_CONTEXTS = {
    "BANK_REFERENCE": A4_REFERENCE_CONTEXT,
    "COUNTERPARTY_ALIAS": A4_ALIAS_CONTEXT,
    "COUNTERPARTY_ACCOUNT": A4_COUNTER_ACCOUNT_CONTEXT,
    "RUN_TRANSACTION": A4_TXN_CONTEXT,
}
# ★ RI-P0-014: ONE_VENDOR_TOKEN_CONTRACT. 세 팀(P1/P2/P3)이 같은 거래처를 같은 토큰으로
# 상호 판독하도록 정규화를 P3 정본 하나로 통일한다("nfkc-ws-latin-casefold-v1").
NORMALIZATION_VERSION = VENDOR_NORMALIZATION_VERSION


class SecureKeyStore(Protocol):
    def root_key(self) -> tuple[str, bytes]: ...


@dataclass(slots=True)
class MemoryKeyStore:
    """Tests only. Production wiring rejects this class (see is_production_provider)."""

    # ★ RI-P0-006/015: file/memory provider 는 test 전용. 제품 조립은 이 provider 를 거부한다.
    is_production_provider: bool = field(default=False, init=False)

    key: bytes = field(default_factory=lambda: secrets.token_bytes(32))
    key_id: str = "test-memory-key-v1"

    def root_key(self) -> tuple[str, bytes]:
        return self.key_id, self.key

    def root_key_existing(self) -> tuple[str, bytes]:
        """Tests model an already-provisioned key; no mutation is required."""

        return self.root_key()


@dataclass(slots=True)
class MacOSKeychainStore:
    # ★ RI-P0-006: 제품 기본 키 저장소는 macOS Keychain only (홈의 평문 파일이 아니다).
    is_production_provider: bool = field(default=True, init=False)

    service: str = "com.butler.accounting.vendor-match.v1"
    account: str = "device-root"

    def _find(self) -> tuple[str, bytes] | None:
        if platform.system() != "Darwin":
            raise AssignmentError(
                "SECURE_KEY_UNAVAILABLE",
                503,
                "The platform secure key store is unavailable.",
            )
        try:
            found = subprocess.run(
                [
                    "/usr/bin/security",
                    "find-generic-password",
                    "-a",
                    self.account,
                    "-s",
                    self.service,
                    "-w",
                ],
                check=False,
                capture_output=True,
                timeout=5,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            raise AssignmentError(
                "SECURE_KEY_UNAVAILABLE",
                503,
                "The platform secure key store is unavailable.",
            ) from exc
        if found.returncode == 0:
            try:
                key = base64.urlsafe_b64decode(found.stdout.strip())
            except Exception as exc:
                raise AssignmentError(
                    "SECURE_KEY_UNAVAILABLE", 503, "The stored key is invalid."
                ) from exc
            if len(key) != 32:
                raise AssignmentError(
                    "SECURE_KEY_UNAVAILABLE", 503, "The stored key is invalid."
                )
            return "macos-keychain-v1", key
        return None

    def root_key_existing(self) -> tuple[str, bytes]:
        """Read a provisioned root without silently creating one.

        A4 observation runs are evidence consumers.  A missing, locked, or
        denied Keychain must therefore fail closed rather than changing device
        key state during classification.
        """

        found = self._find()
        if found is None:
            raise AssignmentError(
                "SECURE_KEY_UNAVAILABLE",
                503,
                "The platform secure key store is unavailable.",
            )
        return found

    def root_key(self) -> tuple[str, bytes]:
        found = self._find()
        if found is not None:
            return found

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
            raise AssignmentError(
                "SECURE_KEY_UNAVAILABLE",
                503,
                "The platform secure key store is unavailable.",
            ) from exc
        if added.returncode != 0:
            raise AssignmentError(
                "SECURE_KEY_UNAVAILABLE",
                503,
                "The platform secure key store rejected key creation.",
            )
        return "macos-keychain-v1", key


def normalize_descriptor(value: str) -> str:
    # ★ RI-P0-014: 독자 casefold 를 제거하고 P3 정본 정규화(Latin-only casefold)에 위임한다.
    try:
        normalized = normalize_vendor_descriptor(value)
    except VendorMatchContractError as exc:
        raise AssignmentError(
            "CANONICAL_TRANSACTION_INVALID", 422, "Descriptor is invalid."
        ) from exc
    if len(normalized) > 500:
        raise AssignmentError(
            "CANONICAL_TRANSACTION_INVALID", 422, "Descriptor is invalid."
        )
    return normalized


def _field(value: str) -> bytes:
    raw = value.encode("utf-8")
    return len(raw).to_bytes(4, "big") + raw


@dataclass(slots=True)
class TokenService:
    key_store: SecureKeyStore

    def _tenant_key(
        self, tenant_id: str, context: bytes, *, require_existing: bool = False
    ) -> tuple[str, bytes]:
        if require_existing:
            existing = getattr(self.key_store, "root_key_existing", None)
            if not callable(existing):
                raise AssignmentError(
                    "SECURE_KEY_UNAVAILABLE",
                    503,
                    "The secure root key cannot be read without provisioning.",
                )
            key_id, root = existing()
        else:
            key_id, root = self.key_store.root_key()
        if len(root) < 32:
            raise AssignmentError(
                "SECURE_KEY_UNAVAILABLE", 503, "The secure root key is invalid."
            )
        return key_id, hmac.new(
            root, context + _field(tenant_id), hashlib.sha256
        ).digest()

    def vendor_token(
        self, tenant_id: str, adapter_family: str, descriptor: str
    ) -> tuple[str, str]:
        key_id, tenant_key = self._tenant_key(tenant_id, MATCH_CONTEXT)
        canonical = normalize_descriptor(descriptor)
        body = (
            _field(tenant_id)
            + _field(adapter_family)
            + _field(NORMALIZATION_VERSION)
            + _field(canonical)
        )
        return key_id, hmac.new(tenant_key, body, hashlib.sha256).hexdigest()

    def account_token(
        self,
        tenant_id: str,
        bank_code: str,
        account_number: str,
    ) -> tuple[str, str]:
        """Return a tenant/bank-scoped own-account token without persisting plaintext.

        The root key remains inside this platform service.  Callers receive only a
        key identifier and HMAC digest, never key bytes or the derived tenant key.
        """

        canonical_account = re.sub(r"[^0-9A-Za-z]", "", str(account_number)).upper()
        canonical_bank = re.sub(r"[^A-Z0-9._:-]", "", str(bank_code).upper())
        if not canonical_account or not 2 <= len(canonical_bank) <= 16:
            raise AssignmentError(
                "CANONICAL_TRANSACTION_INVALID", 422, "Account identity is invalid."
            )
        key_id, tenant_key = self._tenant_key(
            tenant_id, A4_OWN_ACCOUNT_CONTEXT, require_existing=True
        )
        body = _field(tenant_id) + _field(canonical_bank) + _field(canonical_account)
        return key_id, hmac.new(tenant_key, body, hashlib.sha256).hexdigest()

    def provision_a4_account_token(
        self,
        tenant_id: str,
        bank_code: str,
        account_number: str,
    ) -> tuple[str, str]:
        """Provision the tenant root only during an explicit admin registration."""

        canonical_account = re.sub(r"[^0-9A-Za-z]", "", str(account_number)).upper()
        canonical_bank = re.sub(r"[^A-Z0-9._:-]", "", str(bank_code).upper())
        if not canonical_account or not 2 <= len(canonical_bank) <= 16:
            raise AssignmentError(
                "CANONICAL_TRANSACTION_INVALID", 422, "Account identity is invalid."
            )
        key_id, tenant_key = self._tenant_key(
            tenant_id, A4_OWN_ACCOUNT_CONTEXT, require_existing=False
        )
        body = _field(tenant_id) + _field(canonical_bank) + _field(canonical_account)
        return key_id, hmac.new(tenant_key, body, hashlib.sha256).hexdigest()

    def a4_verifier_material(self, tenant_id: str) -> dict[str, str]:
        """Return only tokenization keys needed by the isolated A4 verifier.

        Verification signing authority is deliberately absent.  A separate
        verifier authority owns that key and returns only a signed receipt.
        """

        contexts = {
            "own_account_key_b64": A4_OWN_ACCOUNT_CONTEXT,
            "bank_reference_key_b64": A4_REFERENCE_CONTEXT,
            "counterparty_account_key_b64": A4_COUNTER_ACCOUNT_CONTEXT,
            "run_transaction_key_b64": A4_TXN_CONTEXT,
        }
        material: dict[str, str] = {}
        key_ids: set[str] = set()
        for name, context in contexts.items():
            key_id, key = self._tenant_key(
                tenant_id, context, require_existing=True
            )
            key_ids.add(key_id)
            material[name] = base64.urlsafe_b64encode(key).decode("ascii")
        if len(key_ids) != 1:
            raise AssignmentError(
                "SECURE_KEY_UNAVAILABLE", 503, "The A4 verifier key set is inconsistent."
            )
        material["key_id"] = key_ids.pop()
        material["tenant_id"] = tenant_id
        material["schema_version"] = "butler.box5.a4.verifier_token_keys.v3.2"
        return material

    def a4_evidence_token(
        self,
        tenant_id: str,
        token_kind: str,
        value: str,
    ) -> tuple[str, str]:
        """Tokenize one exact A4 evidence value under a fixed domain allowlist."""

        context = _A4_CONTEXTS.get(token_kind)
        if context is None:
            raise AssignmentError(
                "CANONICAL_TRANSACTION_INVALID", 422, "Evidence token kind is invalid."
            )
        normalized = unicodedata.normalize("NFKC", str(value))
        if any(
            unicodedata.category(character) in {"Cc", "Cf"} for character in normalized
        ):
            raise AssignmentError(
                "CANONICAL_TRANSACTION_INVALID", 422, "Evidence value is invalid."
            )
        normalized = re.sub(r"\s+", " ", normalized).strip()
        if not normalized or len(normalized.encode("utf-8")) > 1_024:
            raise AssignmentError(
                "CANONICAL_TRANSACTION_INVALID", 422, "Evidence value is invalid."
            )
        key_id, tenant_key = self._tenant_key(tenant_id, context, require_existing=True)
        body = _field(tenant_id) + _field(token_kind) + _field(normalized)
        return key_id, hmac.new(tenant_key, body, hashlib.sha256).hexdigest()

    def checkpoint_mac(self, tenant_id: str, event_hash: str) -> str:
        _, key = self._tenant_key(tenant_id, CHECKPOINT_CONTEXT)
        return hmac.new(key, event_hash.encode("ascii"), hashlib.sha256).hexdigest()

    def cursor_mac(self, tenant_id: str, payload: bytes) -> bytes:
        _, key = self._tenant_key(tenant_id, CURSOR_CONTEXT)
        return hmac.new(key, payload, hashlib.sha256).digest()

    def self_test(self, tenant_id: str) -> str:
        key_id, key = self._tenant_key(tenant_id, CHECKPOINT_CONTEXT)
        probe = hmac.new(
            key, b"butler-accounting-keystore-self-test", hashlib.sha256
        ).digest()
        if len(probe) != 32:
            raise AssignmentError(
                "SECURE_KEY_UNAVAILABLE", 503, "The secure key self-test failed."
            )
        return key_id

    @staticmethod
    def idempotency_digest(value: str) -> str:
        return hashlib.sha256(value.encode("utf-8")).hexdigest()
