"""Pinned composition-root authority for Helper1 approval evidence."""
from __future__ import annotations

import base64
import hashlib
import re
import threading
import uuid
from dataclasses import dataclass
from typing import Any, Callable

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from .canonical_json import CanonicalJsonError, canonicalize_butler_cj1, loads_butler_cj1
from .replay_store import ReplayReservation, ReplayReservationStore

EVIDENCE_DOMAIN = b"BUTLER-HELPER1-EVIDENCE-V1\x00"
DIGEST_RE = re.compile(r"^[0-9a-f]{64}$")
KEY_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{7,127}$")
GIT_OID_RE = re.compile(r"^[0-9a-f]{40}(?:[0-9a-f]{24})?$")
SAFE_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/@+-]{0,255}$")

EVIDENCE_SIGNER = "EVIDENCE_SIGNER"
THRESHOLD_POLICY_SIGNER = "THRESHOLD_POLICY_SIGNER"
ALLOWED_KEY_ROLES = frozenset({EVIDENCE_SIGNER, THRESHOLD_POLICY_SIGNER})


class RetrievalPolicyAuthorityError(RuntimeError):
    pass


def _b64url_decode(value: object, *, size: int, code: str) -> bytes:
    if type(value) is not str or not value or "=" in value:
        raise RetrievalPolicyAuthorityError(code)
    try:
        decoded = base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))
    except (ValueError, TypeError) as exc:
        raise RetrievalPolicyAuthorityError(code) from exc
    if len(decoded) != size:
        raise RetrievalPolicyAuthorityError(code)
    return decoded


def _uuid(value: object, code: str) -> str:
    if type(value) is not str:
        raise RetrievalPolicyAuthorityError(code)
    try:
        parsed = uuid.UUID(value)
    except (ValueError, AttributeError) as exc:
        raise RetrievalPolicyAuthorityError(code) from exc
    if str(parsed) != value or parsed.version != 4:
        raise RetrievalPolicyAuthorityError(code)
    return value


def _ppm(value: object, code: str) -> int:
    if type(value) is not int or not 0 <= value <= 1_000_000:
        raise RetrievalPolicyAuthorityError(code)
    return value


@dataclass(frozen=True, slots=True)
class ExpectedSubject:
    commit_sha: str
    tree_sha: str
    workspace_id: str

    def __post_init__(self) -> None:
        if GIT_OID_RE.fullmatch(self.commit_sha) is None:
            raise RetrievalPolicyAuthorityError("TRUST_POLICY_SUBJECT_INVALID")
        if GIT_OID_RE.fullmatch(self.tree_sha) is None:
            raise RetrievalPolicyAuthorityError("TRUST_POLICY_SUBJECT_INVALID")
        _uuid(self.workspace_id, "TRUST_POLICY_SUBJECT_INVALID")


@dataclass(frozen=True, slots=True)
class EncoderIdentity:
    provider: str
    model: str
    revision: str
    artifact_sha256: str

    def __post_init__(self) -> None:
        if any(SAFE_ID_RE.fullmatch(item) is None for item in (self.provider, self.model, self.revision)):
            raise RetrievalPolicyAuthorityError("TRUST_POLICY_ENCODER_INVALID")
        if DIGEST_RE.fullmatch(self.artifact_sha256) is None:
            raise RetrievalPolicyAuthorityError("TRUST_POLICY_ENCODER_INVALID")


@dataclass(frozen=True, slots=True)
class TrustKey:
    key_id: str
    public_key: bytes
    roles: frozenset[str]
    not_before_epoch_s: int
    expires_at_epoch_s: int
    revoked: bool

    def __post_init__(self) -> None:
        if KEY_ID_RE.fullmatch(self.key_id) is None or len(self.public_key) != 32:
            raise RetrievalPolicyAuthorityError("TRUST_KEY_INVALID")
        if not self.roles or not self.roles <= ALLOWED_KEY_ROLES:
            raise RetrievalPolicyAuthorityError("TRUST_KEY_ROLE_INVALID")
        if (
            type(self.not_before_epoch_s) is not int
            or type(self.expires_at_epoch_s) is not int
            or not 0 <= self.not_before_epoch_s < self.expires_at_epoch_s
            or type(self.revoked) is not bool
        ):
            raise RetrievalPolicyAuthorityError("TRUST_KEY_TIME_INVALID")


_SNAPSHOT_TOKEN = object()
_AUTHORITY_TOKEN = object()
_PROVIDER_TOKEN = object()
_SNAPSHOT_REGISTRY: dict[int, tuple[str, int]] = {}
_AUTHORITY_REGISTRY: dict[int, tuple[str, int]] = {}
_CURRENT_POLICY: dict[str, tuple[int, str]] = {}
_REGISTRY_LOCK = threading.Lock()


class TrustPolicySnapshot:
    """Immutable policy minted from composition-owned canonical bytes."""

    __slots__ = (
        "repository", "policy_epoch", "enabled", "keys", "digest",
        "max_evidence_age_seconds", "max_future_skew_seconds", "production_source",
        "subject", "required_strata", "minimum_sample_count",
        "minimum_per_stratum_count", "expected_evaluator_source_sha256",
        "expected_encoder", "expected_corpus_manifest_sha256",
        "expected_index_manifest_policy_sha256", "expected_grounding_threshold_ppm",
        "expected_abstention_threshold_ppm",
    )

    def __init_subclass__(cls, **_: Any) -> None:
        raise TypeError("TRUST_POLICY_SNAPSHOT_FINAL")

    def __init__(
        self,
        token: object,
        *,
        repository: str,
        policy_epoch: int,
        enabled: bool,
        keys: tuple[TrustKey, ...],
        digest: str,
        max_evidence_age_seconds: int,
        max_future_skew_seconds: int,
        production_source: bool,
        subject: ExpectedSubject | None,
        required_strata: frozenset[str],
        minimum_sample_count: int,
        minimum_per_stratum_count: int,
        expected_evaluator_source_sha256: str | None,
        expected_encoder: EncoderIdentity | None,
        expected_corpus_manifest_sha256: str | None,
        expected_index_manifest_policy_sha256: str | None,
        expected_grounding_threshold_ppm: int | None,
        expected_abstention_threshold_ppm: int | None,
    ) -> None:
        if token is not _SNAPSHOT_TOKEN:
            raise RetrievalPolicyAuthorityError("TRUST_POLICY_SNAPSHOT_FORGED")
        values = locals().copy()
        values.pop("self")
        values.pop("token")
        for name, value in values.items():
            object.__setattr__(self, name, value)
        with _REGISTRY_LOCK:
            _SNAPSHOT_REGISTRY[id(self)] = (digest, policy_epoch)

    def __setattr__(self, _: str, __: object) -> None:
        raise AttributeError("TRUST_POLICY_SNAPSHOT_IMMUTABLE")

    def __copy__(self) -> None:
        raise TypeError("TRUST_POLICY_SNAPSHOT_NOT_COPYABLE")

    def __deepcopy__(self, _: object) -> None:
        raise TypeError("TRUST_POLICY_SNAPSHOT_NOT_COPYABLE")

    def __reduce__(self) -> None:
        raise TypeError("TRUST_POLICY_SNAPSHOT_NOT_SERIALIZABLE")

    def key(self, key_id: str, role: str, now_epoch_s: int) -> TrustKey:
        matches = tuple(item for item in self.keys if item.key_id == key_id)
        if len(matches) != 1:
            raise RetrievalPolicyAuthorityError("EVIDENCE_KEY_NOT_PINNED")
        key = matches[0]
        if role not in key.roles:
            raise RetrievalPolicyAuthorityError("EVIDENCE_KEY_ROLE_INVALID")
        if key.revoked:
            raise RetrievalPolicyAuthorityError("EVIDENCE_KEY_REVOKED")
        if not key.not_before_epoch_s <= now_epoch_s < key.expires_at_epoch_s:
            raise RetrievalPolicyAuthorityError("EVIDENCE_KEY_EXPIRED")
        return key

    def is_registered(self) -> bool:
        with _REGISTRY_LOCK:
            return (
                _SNAPSHOT_REGISTRY.get(id(self)) == (self.digest, self.policy_epoch)
                and _CURRENT_POLICY.get(self.repository) == (self.policy_epoch, self.digest)
            )


class ProtectedTrustPolicyProvider:
    """Provider whose policy bytes and digest are fixed by native composition."""

    __slots__ = ("_policy_bytes", "_expected_digest", "_production_source")

    def __init_subclass__(cls, **_: Any) -> None:
        raise TypeError("TRUST_POLICY_PROVIDER_FINAL")

    def __init__(self, token: object, policy_bytes: bytes, expected_digest: str, *, production_source: bool) -> None:
        if token is not _PROVIDER_TOKEN:
            raise RetrievalPolicyAuthorityError("TRUST_POLICY_PROVIDER_FORGED")
        if type(policy_bytes) is not bytes or DIGEST_RE.fullmatch(expected_digest) is None:
            raise RetrievalPolicyAuthorityError("TRUST_POLICY_SOURCE_INVALID")
        if type(production_source) is not bool:
            raise RetrievalPolicyAuthorityError("TRUST_POLICY_SOURCE_INVALID")
        self._policy_bytes = policy_bytes
        self._expected_digest = expected_digest
        self._production_source = production_source

    @classmethod
    def _from_composition_root_bytes(cls, policy_bytes: bytes, expected_digest: str) -> "ProtectedTrustPolicyProvider":
        return cls(_PROVIDER_TOKEN, policy_bytes, expected_digest, production_source=True)

    @classmethod
    def _for_test(cls, policy_bytes: bytes, expected_digest: str) -> "ProtectedTrustPolicyProvider":
        return cls(_PROVIDER_TOKEN, policy_bytes, expected_digest, production_source=False)

    def __copy__(self) -> None:
        raise TypeError("TRUST_POLICY_PROVIDER_NOT_COPYABLE")

    def __deepcopy__(self, _: object) -> None:
        raise TypeError("TRUST_POLICY_PROVIDER_NOT_COPYABLE")

    def __reduce__(self) -> None:
        raise TypeError("TRUST_POLICY_PROVIDER_NOT_SERIALIZABLE")

    def load_snapshot(self) -> TrustPolicySnapshot:
        observed = hashlib.sha256(self._policy_bytes).hexdigest()
        if observed != self._expected_digest:
            raise RetrievalPolicyAuthorityError("TRUST_POLICY_DIGEST_MISMATCH")
        try:
            value = loads_butler_cj1(self._policy_bytes)
        except CanonicalJsonError as exc:
            raise RetrievalPolicyAuthorityError("TRUST_POLICY_CANONICAL_INVALID") from exc
        base_keys = {
            "schema_version", "repository", "policy_epoch", "enabled",
            "max_evidence_age_seconds", "keys",
        }
        enabled_keys = base_keys | {
            "max_future_skew_seconds", "subject", "required_strata",
            "minimum_sample_count", "minimum_per_stratum_count",
            "expected_evaluator_source_sha256", "expected_encoder",
            "expected_corpus_manifest_sha256", "expected_index_manifest_policy_sha256",
            "expected_grounding_threshold_ppm", "expected_abstention_threshold_ppm",
        }
        if type(value) is not dict or set(value) not in (base_keys, enabled_keys):
            raise RetrievalPolicyAuthorityError("TRUST_POLICY_SCHEMA_INVALID")
        if (
            value.get("schema_version") != "butler.helper1.retrieval-approval-trust-policy.v1"
            or type(value.get("repository")) is not str
            or not value["repository"]
            or type(value.get("policy_epoch")) is not int
            or value["policy_epoch"] < 1
            or type(value.get("enabled")) is not bool
            or type(value.get("max_evidence_age_seconds")) is not int
            or not 60 <= value["max_evidence_age_seconds"] <= 86_400
            or type(value.get("keys")) is not list
        ):
            raise RetrievalPolicyAuthorityError("TRUST_POLICY_SCHEMA_INVALID")
        if value["enabled"] != (set(value) == enabled_keys):
            raise RetrievalPolicyAuthorityError("TRUST_POLICY_CONFIGURATION_INVALID")

        keys: list[TrustKey] = []
        for record in value["keys"]:
            if type(record) is not dict or set(record) != {
                "key_id", "public_key_b64url", "roles", "not_before_epoch_s",
                "expires_at_epoch_s", "revoked",
            }:
                raise RetrievalPolicyAuthorityError("TRUST_KEY_INVALID")
            roles = record["roles"]
            if type(roles) is not list or any(type(role) is not str for role in roles):
                raise RetrievalPolicyAuthorityError("TRUST_KEY_ROLE_INVALID")
            keys.append(
                TrustKey(
                    key_id=record["key_id"],
                    public_key=_b64url_decode(record["public_key_b64url"], size=32, code="TRUST_KEY_INVALID"),
                    roles=frozenset(roles),
                    not_before_epoch_s=record["not_before_epoch_s"],
                    expires_at_epoch_s=record["expires_at_epoch_s"],
                    revoked=record["revoked"],
                )
            )
        if len({item.key_id for item in keys}) != len(keys):
            raise RetrievalPolicyAuthorityError("TRUST_KEY_DUPLICATE")
        if value["enabled"] and (
            not keys
            or not any(EVIDENCE_SIGNER in item.roles for item in keys)
            or not any(THRESHOLD_POLICY_SIGNER in item.roles for item in keys)
        ):
            raise RetrievalPolicyAuthorityError("TRUST_POLICY_INCOMPLETE")
        if not value["enabled"] and keys:
            raise RetrievalPolicyAuthorityError("TRUST_POLICY_DISABLED_WITH_KEYS")

        subject = None
        required_strata: frozenset[str] = frozenset()
        minimum_sample_count = minimum_per_stratum_count = 0
        evaluator_digest = corpus_digest = index_digest = None
        encoder = None
        grounding_ppm = abstention_ppm = None
        max_future_skew_seconds = 0
        if value["enabled"]:
            subject_value = value["subject"]
            encoder_value = value["expected_encoder"]
            if type(subject_value) is not dict or set(subject_value) != {"commit_sha", "tree_sha", "workspace_id"}:
                raise RetrievalPolicyAuthorityError("TRUST_POLICY_SUBJECT_INVALID")
            if type(encoder_value) is not dict or set(encoder_value) != {"provider", "model", "revision", "artifact_sha256"}:
                raise RetrievalPolicyAuthorityError("TRUST_POLICY_ENCODER_INVALID")
            subject = ExpectedSubject(**subject_value)
            encoder = EncoderIdentity(**encoder_value)
            strata = value["required_strata"]
            if type(strata) is not list or not strata or any(type(item) is not str or SAFE_ID_RE.fullmatch(item) is None for item in strata):
                raise RetrievalPolicyAuthorityError("TRUST_POLICY_STRATA_INVALID")
            required_strata = frozenset(strata)
            if len(required_strata) != len(strata):
                raise RetrievalPolicyAuthorityError("TRUST_POLICY_STRATA_INVALID")
            minimum_sample_count = value["minimum_sample_count"]
            minimum_per_stratum_count = value["minimum_per_stratum_count"]
            max_future_skew_seconds = value["max_future_skew_seconds"]
            if (
                type(minimum_sample_count) is not int or minimum_sample_count < 1
                or type(minimum_per_stratum_count) is not int or minimum_per_stratum_count < 1
                or type(max_future_skew_seconds) is not int or not 0 <= max_future_skew_seconds <= 300
            ):
                raise RetrievalPolicyAuthorityError("TRUST_POLICY_LIMIT_INVALID")
            evaluator_digest = value["expected_evaluator_source_sha256"]
            corpus_digest = value["expected_corpus_manifest_sha256"]
            index_digest = value["expected_index_manifest_policy_sha256"]
            if any(DIGEST_RE.fullmatch(item) is None for item in (evaluator_digest, corpus_digest, index_digest)):
                raise RetrievalPolicyAuthorityError("TRUST_POLICY_DIGEST_INVALID")
            grounding_ppm = _ppm(value["expected_grounding_threshold_ppm"], "TRUST_POLICY_THRESHOLD_INVALID")
            abstention_ppm = _ppm(value["expected_abstention_threshold_ppm"], "TRUST_POLICY_THRESHOLD_INVALID")

        with _REGISTRY_LOCK:
            current = _CURRENT_POLICY.get(value["repository"])
            candidate = (value["policy_epoch"], observed)
            if current is not None and candidate[0] < current[0]:
                raise RetrievalPolicyAuthorityError("TRUST_POLICY_ROLLBACK")
            if current is not None and candidate[0] == current[0] and candidate[1] != current[1]:
                raise RetrievalPolicyAuthorityError("TRUST_POLICY_EPOCH_CONFLICT")
            _CURRENT_POLICY[value["repository"]] = candidate
        return TrustPolicySnapshot(
            _SNAPSHOT_TOKEN,
            repository=value["repository"],
            policy_epoch=value["policy_epoch"],
            enabled=value["enabled"],
            keys=tuple(keys),
            digest=observed,
            max_evidence_age_seconds=value["max_evidence_age_seconds"],
            max_future_skew_seconds=max_future_skew_seconds,
            production_source=self._production_source,
            subject=subject,
            required_strata=required_strata,
            minimum_sample_count=minimum_sample_count,
            minimum_per_stratum_count=minimum_per_stratum_count,
            expected_evaluator_source_sha256=evaluator_digest,
            expected_encoder=encoder,
            expected_corpus_manifest_sha256=corpus_digest,
            expected_index_manifest_policy_sha256=index_digest,
            expected_grounding_threshold_ppm=grounding_ppm,
            expected_abstention_threshold_ppm=abstention_ppm,
        )


class RetrievalPolicyAuthority:
    """Exact authority accepted by the Helper1 product composition boundary."""

    __slots__ = ("_snapshot", "_replay_store", "_clock")

    def __init_subclass__(cls, **_: Any) -> None:
        raise TypeError("RETRIEVAL_POLICY_AUTHORITY_FINAL")

    def __init__(
        self,
        token: object,
        snapshot: TrustPolicySnapshot,
        replay_store: ReplayReservationStore,
        clock: Callable[[], int],
    ) -> None:
        if token is not _AUTHORITY_TOKEN:
            raise RetrievalPolicyAuthorityError("RETRIEVAL_AUTHORITY_FORGED")
        self._snapshot = snapshot
        self._replay_store = replay_store
        self._clock = clock
        with _REGISTRY_LOCK:
            _AUTHORITY_REGISTRY[id(self)] = (snapshot.digest, snapshot.policy_epoch)

    @classmethod
    def from_composition_root(
        cls,
        provider: ProtectedTrustPolicyProvider,
        replay_store: ReplayReservationStore,
        clock: Callable[[], int],
    ) -> "RetrievalPolicyAuthority":
        if type(provider) is not ProtectedTrustPolicyProvider:
            raise RetrievalPolicyAuthorityError("TRUST_POLICY_PROVIDER_INVALID")
        if not isinstance(replay_store, ReplayReservationStore) or not callable(clock):
            raise RetrievalPolicyAuthorityError("RETRIEVAL_AUTHORITY_DEPENDENCY_INVALID")
        snapshot = provider.load_snapshot()
        if type(snapshot) is not TrustPolicySnapshot or not snapshot.is_registered():
            raise RetrievalPolicyAuthorityError("TRUST_POLICY_SNAPSHOT_INVALID")
        return cls(_AUTHORITY_TOKEN, snapshot, replay_store, clock)

    def __copy__(self) -> None:
        raise TypeError("RETRIEVAL_AUTHORITY_NOT_COPYABLE")

    def __deepcopy__(self, _: object) -> None:
        raise TypeError("RETRIEVAL_AUTHORITY_NOT_COPYABLE")

    def __reduce__(self) -> None:
        raise TypeError("RETRIEVAL_AUTHORITY_NOT_SERIALIZABLE")

    @property
    def snapshot(self) -> TrustPolicySnapshot:
        return self._snapshot

    @property
    def is_production_authority(self) -> bool:
        return type(self) is RetrievalPolicyAuthority and self.is_current() and self._snapshot.enabled and self._snapshot.production_source

    def now(self) -> int:
        value = self._clock()
        if type(value) is not int or value < 1:
            raise RetrievalPolicyAuthorityError("TRUSTED_CLOCK_INVALID")
        return value

    def is_current(self) -> bool:
        if type(self) is not RetrievalPolicyAuthority or not self._snapshot.is_registered():
            return False
        with _REGISTRY_LOCK:
            return _AUTHORITY_REGISTRY.get(id(self)) == (self._snapshot.digest, self._snapshot.policy_epoch)

    def verify_signature(
        self,
        *,
        key_id: str,
        role: str,
        signed: dict[str, Any],
        signature_b64u: object,
        now_epoch_s: int,
    ) -> None:
        key_role = THRESHOLD_POLICY_SIGNER if role == "A4_RETRIEVAL_THRESHOLD_POLICY" else EVIDENCE_SIGNER
        key = self._snapshot.key(key_id, key_role, now_epoch_s)
        signature = _b64url_decode(signature_b64u, size=64, code="EVIDENCE_SIGNATURE_INVALID")
        try:
            Ed25519PublicKey.from_public_bytes(key.public_key).verify(
                signature,
                EVIDENCE_DOMAIN + canonicalize_butler_cj1(signed),
            )
        except (InvalidSignature, ValueError, CanonicalJsonError) as exc:
            raise RetrievalPolicyAuthorityError("EVIDENCE_SIGNATURE_INVALID") from exc

    def reserve(self, reservations: tuple[ReplayReservation, ...], now_epoch_s: int) -> None:
        if not self.is_current():
            raise RetrievalPolicyAuthorityError("RETRIEVAL_AUTHORITY_STALE")
        self._replay_store.reserve_many(reservations, now_epoch_s=now_epoch_s)
