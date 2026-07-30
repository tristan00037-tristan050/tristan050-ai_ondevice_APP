"""Process-local Helper1 service registry and replay authority.

Native bootstrap is the only product authority allowed to register a ready
workspace. HTTP callers can query an existing workspace but cannot inject
paths, model locations, keys, folder handles, or runner binaries.
"""
from __future__ import annotations

import threading
import time
import uuid
from collections import OrderedDict
from dataclasses import dataclass, field
from typing import Any

from .contracts import AnswerKind, AnswerResult, require_uuid
from .pipeline import Helper1AnswerPipeline


class Helper1ServiceError(RuntimeError):
    pass


@dataclass
class RequestReplayGuard:
    """Bounded process-local one-shot request authority.

    The capability middleware authenticates the local caller. This guard then
    prevents a previously accepted request envelope from being replayed during
    the sidecar lifetime. Persistent/native nonce authority remains a release
    prerequisite and is not claimed by this implementation.
    """

    ttl_seconds: int = 24 * 60 * 60
    maximum_entries: int = 100_000
    _seen: OrderedDict[str, float] = field(default_factory=OrderedDict, init=False)
    _lock: threading.Lock = field(default_factory=threading.Lock, init=False)

    def __post_init__(self) -> None:
        if (
            isinstance(self.ttl_seconds, bool)
            or not isinstance(self.ttl_seconds, int)
            or not 60 <= self.ttl_seconds <= 7 * 24 * 60 * 60
            or isinstance(self.maximum_entries, bool)
            or not isinstance(self.maximum_entries, int)
            or not 1_000 <= self.maximum_entries <= 1_000_000
        ):
            raise Helper1ServiceError("REPLAY_GUARD_CONFIG_INVALID")

    def claim(self, request_id: str) -> bool:
        require_uuid(request_id, "REQUEST_ID_INVALID")
        now = time.monotonic()
        cutoff = now - self.ttl_seconds
        with self._lock:
            while self._seen:
                oldest_id, observed = next(iter(self._seen.items()))
                if observed >= cutoff:
                    break
                self._seen.pop(oldest_id)
            if request_id in self._seen:
                return False
            self._seen[request_id] = now
            while len(self._seen) > self.maximum_entries:
                self._seen.popitem(last=False)
            return True


@dataclass
class Helper1Service:
    _pipelines: dict[str, Helper1AnswerPipeline] = field(default_factory=dict)
    _states: dict[str, str] = field(default_factory=dict)
    _lock: threading.RLock = field(default_factory=threading.RLock, init=False)
    _replay: RequestReplayGuard = field(default_factory=RequestReplayGuard, init=False)

    def register_native_pipeline(
        self, workspace_id: str, pipeline: Helper1AnswerPipeline
    ) -> None:
        require_uuid(workspace_id, "WORKSPACE_ID_INVALID")
        if pipeline.index.manifest.workspace_id != workspace_id:
            raise Helper1ServiceError("WORKSPACE_INDEX_MISMATCH")
        if not pipeline.effect_authority.key_provider.is_production_provider:
            raise Helper1ServiceError("PRODUCTION_KEY_PROVIDER_REQUIRED")
        with self._lock:
            self._pipelines[workspace_id] = pipeline
            self._states[workspace_id] = "READY"

    def register_test_pipeline(
        self, workspace_id: str, pipeline: Helper1AnswerPipeline
    ) -> None:
        """Explicit test seam that can never become HTTP-answer ready."""
        require_uuid(workspace_id, "WORKSPACE_ID_INVALID")
        if pipeline.index.manifest.workspace_id != workspace_id:
            raise Helper1ServiceError("WORKSPACE_INDEX_MISMATCH")
        with self._lock:
            self._pipelines[workspace_id] = pipeline
            self._states[workspace_id] = "READY_TEST_ONLY"

    def unregister(self, workspace_id: str, *, state: str = "ASSET_MISSING") -> None:
        require_uuid(workspace_id, "WORKSPACE_ID_INVALID")
        if state not in {
            "ASSET_MISSING",
            "INDEXING",
            "VERIFYING",
            "INDEX_INVALID",
            "STALE",
            "FAILED",
        }:
            raise Helper1ServiceError("WORKSPACE_STATE_INVALID")
        with self._lock:
            self._pipelines.pop(workspace_id, None)
            self._states[workspace_id] = state

    def _product_pipeline(self, workspace_id: str) -> Helper1AnswerPipeline | None:
        require_uuid(workspace_id, "WORKSPACE_ID_INVALID")
        with self._lock:
            if self._states.get(workspace_id) != "READY":
                return None
            return self._pipelines.get(workspace_id)

    def status(self, workspace_id: str | None = None) -> dict[str, Any]:
        if workspace_id is not None:
            require_uuid(workspace_id, "WORKSPACE_ID_INVALID")
        with self._lock:
            if workspace_id is None:
                workspaces = [
                    {
                        "workspace_id": identifier,
                        "state": self._states.get(identifier, "ASSET_MISSING"),
                    }
                    for identifier in sorted(set(self._states) | set(self._pipelines))
                ]
                return {
                    "schema_version": "butler.helper1.status.v2",
                    "state": (
                        "READY"
                        if any(item["state"] == "READY" for item in workspaces)
                        else "ASSET_MISSING"
                    ),
                    "workspaces": workspaces,
                    "product_release_allowed": False,
                    "runtime_activation_allowed": False,
                    "production_claim_allowed": False,
                    "external_network_allowed": False,
                }
            pipeline = self._pipelines.get(workspace_id)
            state = self._states.get(
                workspace_id, "READY" if pipeline else "ASSET_MISSING"
            )
            product_pipeline = pipeline if state == "READY" else None
            return {
                "schema_version": "butler.helper1.status.v2",
                "workspace_id": workspace_id,
                "state": state,
                "generation_id": (
                    product_pipeline.index.manifest.generation_id
                    if product_pipeline
                    else None
                ),
                "index_manifest_sha256": (
                    product_pipeline.index.manifest.digest if product_pipeline else None
                ),
                "product_release_allowed": False,
                "runtime_activation_allowed": False,
                "production_claim_allowed": False,
                "external_network_allowed": False,
            }

    @staticmethod
    def _refusal(
        *,
        kind: AnswerKind,
        request_id: str,
        workspace_id: str,
        reason_code: str,
        pipeline: Helper1AnswerPipeline | None = None,
    ) -> AnswerResult:
        return AnswerResult(
            kind=kind,
            request_id=request_id,
            workspace_id=workspace_id,
            generation_id=(
                pipeline.index.manifest.generation_id if pipeline else None
            ),
            answer=None,
            reason_code=reason_code,
            model_identity_sha256=None,
            index_manifest_sha256=(
                pipeline.index.manifest.digest if pipeline else None
            ),
        )

    def _authorize_request(
        self,
        *,
        workspace_id: str,
        request_id: str,
        requested_generation_id: str | None,
        effect_intent: str,
    ) -> tuple[Helper1AnswerPipeline | None, AnswerResult | None]:
        require_uuid(workspace_id, "WORKSPACE_ID_INVALID")
        require_uuid(request_id, "REQUEST_ID_INVALID")
        if requested_generation_id is not None:
            require_uuid(
                requested_generation_id, "REQUESTED_GENERATION_ID_INVALID"
            )
        if effect_intent != "display_only":
            return None, self._refusal(
                kind=AnswerKind.REFUSED_POLICY,
                request_id=request_id,
                workspace_id=workspace_id,
                reason_code="EFFECT_INTENT_NOT_AUTHORIZED",
            )
        if not self._replay.claim(request_id):
            return None, self._refusal(
                kind=AnswerKind.REFUSED_POLICY,
                request_id=request_id,
                workspace_id=workspace_id,
                reason_code="REQUEST_REPLAYED",
            )
        pipeline = self._product_pipeline(workspace_id)
        if pipeline is None:
            return None, self._refusal(
                kind=AnswerKind.REFUSED_ASSET_MISSING,
                request_id=request_id,
                workspace_id=workspace_id,
                reason_code="HELPER1_RUNTIME_NOT_BOOTSTRAPPED",
            )
        if (
            requested_generation_id is not None
            and requested_generation_id != pipeline.index.manifest.generation_id
        ):
            return None, self._refusal(
                kind=AnswerKind.REFUSED_INDEX_INVALID,
                request_id=request_id,
                workspace_id=workspace_id,
                reason_code="REQUESTED_GENERATION_NOT_ACTIVE",
                pipeline=pipeline,
            )
        return pipeline, None

    def ask(
        self,
        *,
        workspace_id: str,
        query: str,
        top_k: int,
        request_id: str,
        requested_generation_id: str | None,
        effect_intent: str,
    ) -> AnswerResult:
        pipeline, refusal = self._authorize_request(
            workspace_id=workspace_id,
            request_id=request_id,
            requested_generation_id=requested_generation_id,
            effect_intent=effect_intent,
        )
        if refusal is not None:
            return refusal
        assert pipeline is not None
        return pipeline.ask(
            query=query,
            workspace_id=workspace_id,
            top_k=top_k,
            request_id=request_id,
        )

    def search(
        self,
        *,
        workspace_id: str,
        query: str,
        top_k: int,
        request_id: str,
        requested_generation_id: str | None,
        effect_intent: str,
    ) -> tuple[int, dict[str, Any]]:
        pipeline, refusal = self._authorize_request(
            workspace_id=workspace_id,
            request_id=request_id,
            requested_generation_id=requested_generation_id,
            effect_intent=effect_intent,
        )
        if refusal is not None:
            return refusal.http_status, refusal.to_public_dict()
        assert pipeline is not None
        try:
            chunks = pipeline.search(query, top_k)
        except Exception:
            refusal = self._refusal(
                kind=AnswerKind.REFUSED_INDEX_INVALID,
                request_id=request_id,
                workspace_id=workspace_id,
                reason_code="INDEX_OR_EMBEDDING_INVALID",
                pipeline=pipeline,
            )
            return refusal.http_status, refusal.to_public_dict()
        return 200, {
            "schema_version": "butler.helper1.search.v2",
            "kind": "SEARCHED",
            "request_id": request_id,
            "workspace_id": workspace_id,
            "generation_id": pipeline.index.manifest.generation_id,
            "index_manifest_sha256": pipeline.index.manifest.digest,
            "results": [
                {
                    "chunk_id": chunk.chunk_id,
                    "source_id": chunk.source_id,
                    "dense_score": chunk.dense_score,
                    "lexical_score": chunk.lexical_score,
                    "fused_score": chunk.fused_score,
                }
                for chunk in chunks
            ],
        }


_SERVICE = Helper1Service()


def get_helper1_service() -> Helper1Service:
    return _SERVICE
