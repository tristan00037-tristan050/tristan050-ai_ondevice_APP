"""Single terminal Helper1 release authority and signed receipt v2."""
from __future__ import annotations

import base64
import hmac
from dataclasses import dataclass
from typing import Any

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)

from butler_pc_core.connect_loop.dlp_guard import scan_runtime_text

from .contracts import (
    Citation,
    TerminalLatch,
    canonical_json,
    require_digest,
    require_safe_id,
    require_uuid,
    sha256_bytes,
)
from .security import Helper1SecurityError, KeyProvider, derive_subkey
from .trace import RunTrace, TraceError

ORDERED_GATES = (
    "QUERY_AUTHORIZED",
    "INDEX_VERIFIED",
    "RETRIEVED",
    "PRE_GROUNDING_PASSED",
    "GENERATED_BUFFERED",
    "CLAIMS_VERIFIED",
    "DLP_PASSED",
    "EFFECT_AUTHORIZED",
    "OS_EGRESS_VERIFIED",
    "RELEASED",
)


@dataclass(frozen=True)
class ReleaseReceipt:
    request_id: str
    workspace_id: str
    generation_id: str
    policy_sha256: str
    gate_bundle_sha256: str
    ordered_trace_root: str
    authority_key_id: str
    signature: str
    terminal_count: int
    ordered_gates: tuple[str, ...] = ORDERED_GATES
    schema_version: str = "butler.helper1.release-receipt.v2"

    def __post_init__(self) -> None:
        if self.schema_version != "butler.helper1.release-receipt.v2":
            raise Helper1SecurityError("RELEASE_SCHEMA_INVALID")
        require_uuid(self.request_id, "REQUEST_ID_INVALID")
        require_uuid(self.workspace_id, "WORKSPACE_ID_INVALID")
        require_uuid(self.generation_id, "GENERATION_ID_INVALID")
        require_digest(self.policy_sha256, "RELEASE_POLICY_DIGEST_INVALID")
        require_digest(self.gate_bundle_sha256, "RELEASE_GATE_BUNDLE_INVALID")
        require_digest(self.ordered_trace_root, "RELEASE_TRACE_ROOT_INVALID")
        require_safe_id(self.authority_key_id, "RELEASE_AUTHORITY_KEY_INVALID")
        if (
            not isinstance(self.signature, str)
            or len(self.signature) != 86
            or any(
                character
                not in "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789_-"
                for character in self.signature
            )
        ):
            raise Helper1SecurityError("RELEASE_SIGNATURE_INVALID")
        if self.terminal_count != 1:
            raise Helper1SecurityError("RELEASE_TERMINAL_COUNT_INVALID")
        if self.ordered_gates != ORDERED_GATES:
            raise Helper1SecurityError("RELEASE_GATE_ORDER_INVALID")

    def unsigned_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "request_id": self.request_id,
            "workspace_id": self.workspace_id,
            "generation_id": self.generation_id,
            "policy_sha256": self.policy_sha256,
            "gate_bundle_sha256": self.gate_bundle_sha256,
            "ordered_trace_root": self.ordered_trace_root,
            "authority_key_id": self.authority_key_id,
            "terminal_count": self.terminal_count,
            "ordered_gates": list(self.ordered_gates),
        }

    def to_dict(self) -> dict[str, Any]:
        return {**self.unsigned_dict(), "signature": self.signature}

    @property
    def digest(self) -> str:
        return sha256_bytes(canonical_json(self.to_dict()))


@dataclass
class ExternalEffectAuthority:
    key_provider: KeyProvider

    REQUIRED_GATES: tuple[str, ...] = ORDERED_GATES[:-1]

    def _private_key(self, workspace_id: str) -> tuple[str, Ed25519PrivateKey]:
        key_id, master = self.key_provider.key(workspace_id)
        seed = derive_subkey(master, b"external-effect-ed25519")
        if len(seed) != 32:
            raise Helper1SecurityError("RELEASE_KEY_INVALID")
        return key_id, Ed25519PrivateKey.from_private_bytes(seed)

    def release_display(
        self,
        *,
        request_id: str,
        workspace_id: str,
        generation_id: str,
        answer: str,
        citations: tuple[Citation, ...],
        model_identity_sha256: str,
        index_manifest_sha256: str,
        policy_sha256: str,
        egress_observation_sha256: str | None,
        trace: RunTrace | None,
        completed_gates: tuple[str, ...],
        latch: TerminalLatch,
    ) -> ReleaseReceipt:
        if completed_gates != self.REQUIRED_GATES:
            raise Helper1SecurityError("RELEASE_GATE_ORDER_INVALID")
        require_digest(model_identity_sha256, "RELEASE_MODEL_IDENTITY_INVALID")
        require_digest(index_manifest_sha256, "RELEASE_INDEX_IDENTITY_INVALID")
        require_digest(policy_sha256, "RELEASE_POLICY_DIGEST_INVALID")
        if self.key_provider.is_production_provider:
            require_digest(
                egress_observation_sha256,
                "RELEASE_EGRESS_OBSERVATION_INVALID",
            )
            if trace is None:
                raise Helper1SecurityError("RELEASE_TRACE_REQUIRED")
        if not answer or not citations:
            raise Helper1SecurityError("RELEASE_PAYLOAD_INVALID")
        citation_value = [citation.to_dict() for citation in citations]
        dlp = scan_runtime_text(answer)
        if not dlp["passed"]:
            raise Helper1SecurityError("RELEASE_DLP_BLOCKED")
        gate_bundle = {
            "answer_sha256": sha256_bytes(answer.encode("utf-8")),
            "citations_sha256": sha256_bytes(canonical_json(citation_value)),
            "model_identity_sha256": model_identity_sha256,
            "index_manifest_sha256": index_manifest_sha256,
            "policy_sha256": policy_sha256,
            "egress_observation_sha256": egress_observation_sha256,
            "ordered_trace_root_before_terminal": trace.root if trace is not None else None,
            "effect": "display",
            "completed_gates": list(completed_gates),
        }
        gate_bundle_sha256 = sha256_bytes(canonical_json(gate_bundle))
        latch.commit("ANSWERED")
        if trace is not None:
            try:
                trace.terminal("ANSWERED")
                trace.verify_complete()
            except TraceError as exc:
                raise Helper1SecurityError("RELEASE_TRACE_INVALID") from exc
        trace_root = trace.root if trace is not None else "0" * 64
        key_id, private_key = self._private_key(workspace_id)
        unsigned = {
            "schema_version": "butler.helper1.release-receipt.v2",
            "request_id": request_id,
            "workspace_id": workspace_id,
            "generation_id": generation_id,
            "policy_sha256": policy_sha256,
            "gate_bundle_sha256": gate_bundle_sha256,
            "ordered_trace_root": trace_root,
            "authority_key_id": key_id,
            "terminal_count": latch.count,
            "ordered_gates": ORDERED_GATES,
        }
        signature = base64.urlsafe_b64encode(
            private_key.sign(canonical_json(unsigned))
        ).rstrip(b"=").decode("ascii")
        return ReleaseReceipt(**unsigned, signature=signature)

    def verify(self, receipt: ReleaseReceipt) -> bool:
        key_id, private_key = self._private_key(receipt.workspace_id)
        if key_id != receipt.authority_key_id:
            return False
        try:
            signature = base64.urlsafe_b64decode(receipt.signature + "==")
            public_key: Ed25519PublicKey = private_key.public_key()
            public_key.verify(signature, canonical_json(receipt.unsigned_dict()))
        except (InvalidSignature, ValueError):
            return False
        return True
