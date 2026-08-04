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
from dataclasses import asdict, dataclass, field, replace
from typing import Any

from .contracts import (
    AnswerKind,
    AnswerResult,
    Helper1ContractError,
    canonical_json,
    require_digest,
    require_uuid,
    sha256_bytes,
)
from .approval_closure import ApprovalState, ClosureVerdict
from .execution import ExecutionAuthorityError, NativeExecutionAuthority
from .index_store import LoadedIndex
from .measurement import (
    MeasurementError,
    NativeEgressMeasurementAuthority,
    VerifiedEgressObservation,
)
from .pipeline import Helper1AnswerPipeline, NativeIndexOperation
from .release import ExternalEffectAuthority
from .retrieval import HybridRetriever, RetrievalPolicy
from .retrieval_policy import RetrievalPolicyAuthority
from .security import MacOSKeychainProvider
from .trace import RunTrace


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
    _execution_authorities: dict[str, NativeExecutionAuthority] = field(default_factory=dict)
    _retrieval_policy_authorities: dict[str, RetrievalPolicyAuthority] = field(
        default_factory=dict
    )
    _closure_verdicts: dict[str, ClosureVerdict] = field(default_factory=dict)
    _session_digests: dict[str, str] = field(default_factory=dict)
    _pending_indexes: dict[str, LoadedIndex] = field(default_factory=dict)
    _lock: threading.RLock = field(default_factory=threading.RLock, init=False)
    _replay: RequestReplayGuard = field(default_factory=RequestReplayGuard, init=False)

    @staticmethod
    def _activation_grant_covers(
        authority: NativeExecutionAuthority,
        *,
        workspace_id: str,
        generation_id: str,
        manifest_sha256: str,
    ) -> bool:
        """Require the signed grant to bind both generation and index bytes."""
        return (
            type(authority) is NativeExecutionAuthority
            and authority.is_production_authority is True
            and authority.grant.workspace_id == workspace_id
            and authority.grant.generation_id == generation_id
            and manifest_sha256 in authority.grant.artifact_digests
        )

    def register_native_pipeline(
        self,
        workspace_id: str,
        pipeline: Helper1AnswerPipeline,
        *,
        execution_authority: NativeExecutionAuthority,
        session_digest: str,
        retrieval_policy_authority: RetrievalPolicyAuthority | None = None,
        closure_verdict: ClosureVerdict | None = None,
    ) -> None:
        require_uuid(workspace_id, "WORKSPACE_ID_INVALID")
        if type(pipeline) is not Helper1AnswerPipeline:
            raise Helper1ServiceError("PRODUCTION_PIPELINE_TYPE_REQUIRED")
        if pipeline.index.manifest.workspace_id != workspace_id:
            raise Helper1ServiceError("WORKSPACE_INDEX_MISMATCH")
        if (
            type(pipeline.effect_authority) is not ExternalEffectAuthority
            or type(pipeline.effect_authority.key_provider) is not MacOSKeychainProvider
        ):
            raise Helper1ServiceError("PRODUCTION_KEY_PROVIDER_REQUIRED")
        if (
            type(pipeline.retriever) is not HybridRetriever
            or type(pipeline.retriever.policy) is not RetrievalPolicy
            or not pipeline.retriever.policy.is_calibrated
        ):
            raise Helper1ServiceError("BLOCK_RETRIEVAL_POLICY_UNCALIBRATED")
        if (
            type(pipeline.measurement_authority) is not NativeEgressMeasurementAuthority
            or not pipeline.measurement_authority.is_production_observer
        ):
            raise Helper1ServiceError("PRODUCTION_EGRESS_OBSERVER_REQUIRED")
        if (
            pipeline.index_operation is not None
            and type(pipeline.index_operation) is not NativeIndexOperation
        ):
            raise Helper1ServiceError("PRODUCTION_INDEX_AUTHORITY_REQUIRED")
        if type(execution_authority) is not NativeExecutionAuthority:
            raise Helper1ServiceError("PRODUCTION_EXECUTION_AUTHORITY_REQUIRED")
        if (
            type(retrieval_policy_authority) is not RetrievalPolicyAuthority
            or not retrieval_policy_authority.is_production_authority
            or not retrieval_policy_authority.is_current()
        ):
            raise Helper1ServiceError("PRODUCTION_RETRIEVAL_AUTHORITY_REQUIRED")
        if (
            type(closure_verdict) is not ClosureVerdict
            or closure_verdict.state is not ApprovalState.RELEASE_ALLOWED
            or not closure_verdict.release_allowed
            or closure_verdict.policy_sha256
            != retrieval_policy_authority.snapshot.digest
            or closure_verdict.policy_epoch
            != retrieval_policy_authority.snapshot.policy_epoch
            or closure_verdict.evidence_set_sha256
            not in execution_authority.grant.artifact_digests
        ):
            raise Helper1ServiceError("HELPER1_APPROVAL_CLOSURE_REQUIRED")
        require_digest(session_digest, "SESSION_DIGEST_INVALID")
        if not self._activation_grant_covers(
            execution_authority,
            workspace_id=workspace_id,
            generation_id=pipeline.index.manifest.generation_id,
            manifest_sha256=pipeline.index.manifest.digest,
        ):
            raise Helper1ServiceError("ACTIVATION_ARTIFACT_BINDING_MISMATCH")
        with self._lock:
            self._pipelines[workspace_id] = pipeline
            self._execution_authorities[workspace_id] = execution_authority
            self._retrieval_policy_authorities[workspace_id] = retrieval_policy_authority
            self._closure_verdicts[workspace_id] = closure_verdict
            self._session_digests[workspace_id] = session_digest
            self._pending_indexes.pop(workspace_id, None)
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
            self._execution_authorities.pop(workspace_id, None)
            self._retrieval_policy_authorities.pop(workspace_id, None)
            self._closure_verdicts.pop(workspace_id, None)
            self._session_digests.pop(workspace_id, None)
            self._pending_indexes.pop(workspace_id, None)
            self._states[workspace_id] = state

    def activate_index_candidate(
        self,
        *,
        workspace_id: str,
        generation_id: str,
        execution_authority: NativeExecutionAuthority,
    ) -> None:
        """Activate an observed candidate only after a signed native grant exists."""
        require_uuid(workspace_id, "WORKSPACE_ID_INVALID")
        require_uuid(generation_id, "GENERATION_ID_INVALID")
        with self._lock:
            pipeline = self._pipelines.get(workspace_id)
            candidate = self._pending_indexes.get(workspace_id)
            if (
                self._states.get(workspace_id) != "READY"
                or pipeline is None
                or type(pipeline.index_operation) is not NativeIndexOperation
                or candidate is None
                or candidate.manifest.generation_id != generation_id
                or candidate.manifest.previous_generation_id
                != pipeline.index.manifest.generation_id
            ):
                raise Helper1ServiceError("INDEX_CANDIDATE_NOT_PENDING")
            if not self._activation_grant_covers(
                execution_authority,
                workspace_id=workspace_id,
                generation_id=generation_id,
                manifest_sha256=candidate.manifest.digest,
            ):
                raise Helper1ServiceError("INDEX_ACTIVATION_AUTHORITY_INVALID")
            closure_verdict = self._closure_verdicts.get(workspace_id)
            retrieval_authority = self._retrieval_policy_authorities.get(workspace_id)
            if (
                type(closure_verdict) is not ClosureVerdict
                or not closure_verdict.release_allowed
                or closure_verdict.evidence_set_sha256
                not in execution_authority.grant.artifact_digests
                or type(retrieval_authority) is not RetrievalPolicyAuthority
                or not retrieval_authority.is_production_authority
                or not retrieval_authority.is_current()
            ):
                raise Helper1ServiceError("INDEX_APPROVAL_CLOSURE_INVALID")
            activated = pipeline.index_operation.activate_candidate(
                candidate=candidate,
                previous_generation_id=pipeline.index.manifest.generation_id,
            )
            if activated.manifest.digest != candidate.manifest.digest:
                raise Helper1ServiceError("INDEX_ACTIVATION_VERIFY_FAILED")
            self._pipelines[workspace_id] = replace(pipeline, index=activated)
            self._execution_authorities[workspace_id] = execution_authority
            self._pending_indexes.pop(workspace_id, None)

    def _product_context(
        self, workspace_id: str
    ) -> tuple[Helper1AnswerPipeline, NativeExecutionAuthority, str] | None:
        require_uuid(workspace_id, "WORKSPACE_ID_INVALID")
        with self._lock:
            if self._states.get(workspace_id) != "READY":
                return None
            pipeline = self._pipelines.get(workspace_id)
            authority = self._execution_authorities.get(workspace_id)
            retrieval_authority = self._retrieval_policy_authorities.get(workspace_id)
            closure_verdict = self._closure_verdicts.get(workspace_id)
            session_digest = self._session_digests.get(workspace_id)
            if (
                pipeline is None
                or authority is None
                or session_digest is None
                or type(retrieval_authority) is not RetrievalPolicyAuthority
                or not retrieval_authority.is_production_authority
                or not retrieval_authority.is_current()
                or type(closure_verdict) is not ClosureVerdict
                or not closure_verdict.release_allowed
                or closure_verdict.policy_sha256 != retrieval_authority.snapshot.digest
                or closure_verdict.policy_epoch != retrieval_authority.snapshot.policy_epoch
            ):
                return None
            return pipeline, authority, session_digest

    def _product_pipeline(self, workspace_id: str) -> Helper1AnswerPipeline | None:
        context = self._product_context(workspace_id)
        return context[0] if context is not None else None

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
                "approval_state": (
                    self._closure_verdicts[workspace_id].state.value
                    if workspace_id in self._closure_verdicts
                    else ApprovalState.DISABLED.value
                ),
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
        client_request_id: str,
        requested_generation_id: str | None,
        effect_intent: str,
        session_digest: str,
        expected_effect_intent: str = "display_only",
    ) -> tuple[Helper1AnswerPipeline | None, AnswerResult | None]:
        require_uuid(workspace_id, "WORKSPACE_ID_INVALID")
        require_uuid(request_id, "REQUEST_ID_INVALID")
        require_uuid(client_request_id, "CLIENT_REQUEST_ID_INVALID")
        require_digest(session_digest, "SESSION_DIGEST_INVALID")
        if requested_generation_id is not None:
            require_uuid(
                requested_generation_id, "REQUESTED_GENERATION_ID_INVALID"
            )
        if effect_intent != expected_effect_intent:
            return None, self._refusal(
                kind=AnswerKind.REFUSED_POLICY,
                request_id=request_id,
                workspace_id=workspace_id,
                reason_code="EFFECT_INTENT_NOT_AUTHORIZED",
            )
        if not self._replay.claim(client_request_id):
            return None, self._refusal(
                kind=AnswerKind.REFUSED_POLICY,
                request_id=request_id,
                workspace_id=workspace_id,
                reason_code="REQUEST_REPLAYED",
            )
        context = self._product_context(workspace_id)
        if context is None:
            return None, self._refusal(
                kind=AnswerKind.REFUSED_ASSET_MISSING,
                request_id=request_id,
                workspace_id=workspace_id,
                reason_code="HELPER1_RUNTIME_NOT_BOOTSTRAPPED",
            )
        pipeline, _authority, registered_session_digest = context
        if registered_session_digest != session_digest:
            return None, self._refusal(
                kind=AnswerKind.REFUSED_POLICY,
                request_id=request_id,
                workspace_id=workspace_id,
                reason_code="CAPABILITY_SESSION_NOT_BOUND",
                pipeline=pipeline,
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

    @staticmethod
    def _start_trace(
        *,
        pipeline: Helper1AnswerPipeline,
        request_id: str,
        workspace_id: str,
        session_digest: str,
        action: str,
        input_chars: int,
        top_k: int | None,
        effect_intent: str,
    ) -> RunTrace:
        trace = RunTrace(
            request_id=request_id,
            workspace_id=workspace_id,
            generation_id=pipeline.index.manifest.generation_id,
            session_digest=session_digest,
            action=action,
        )
        trace.append(
            "STRICT_REQUEST_DECODED",
            {"input_chars": input_chars, "top_k": top_k},
        )
        trace.append("AUTHORIZATION_RESOLVED", {"effect_intent": effect_intent})
        trace.append("RUN_NONCE_CREATED", {"run_id": trace.run_id})
        trace.append(
            "TRUST_POLICY_LOADED",
            {"policy_sha256": pipeline.index.manifest.policy_sha256},
        )
        trace.append(
            "MODEL_CLOSURE_VERIFIED",
            {"model_identity_sha256": pipeline.generator.identity_sha256},
        )
        trace.append(
            "INDEX_MANIFEST_VERIFIED",
            {"index_manifest_sha256": pipeline.index.manifest.digest},
        )
        return trace

    @staticmethod
    def _append_observed_operation(
        *,
        trace: RunTrace,
        operation_metadata: dict[str, Any],
        content_metadata: dict[str, Any],
        observation: VerifiedEgressObservation,
    ) -> None:
        trace.append("RETRIEVAL_COMPLETED", operation_metadata)
        trace.append("CURRENT_CHUNK_BYTES_VERIFIED", content_metadata)
        for name in (
            "GROUNDING_AND_INJECTION_PASSED",
            "GENERATION_BUFFERED",
            "CLAIMS_VERIFIED",
            "DLP_PASSED",
            "EFFECT_AUTHORIZED",
        ):
            trace.append(name, {"status": "NOT_APPLICABLE"})
        trace.append(
            "OS_EGRESS_VERIFIED",
            {
                "raw_observation_sha256": observation.raw_observation_sha256,
                "external_send_zero": observation.external_send_zero,
            },
        )

    def ask(
        self,
        *,
        workspace_id: str,
        query: str,
        top_k: int,
        request_id: str,
        client_request_id: str,
        requested_generation_id: str | None,
        effect_intent: str,
        session_digest: str,
    ) -> AnswerResult:
        pipeline, refusal = self._authorize_request(
            workspace_id=workspace_id,
            request_id=request_id,
            client_request_id=client_request_id,
            requested_generation_id=requested_generation_id,
            effect_intent=effect_intent,
            session_digest=session_digest,
        )
        if refusal is not None:
            return refusal
        assert pipeline is not None
        trace = self._start_trace(
            pipeline=pipeline,
            request_id=request_id,
            workspace_id=workspace_id,
            session_digest=session_digest,
            action="ask",
            input_chars=len(query),
            top_k=top_k,
            effect_intent=effect_intent,
        )
        result = pipeline.ask(
            query=query,
            workspace_id=workspace_id,
            top_k=top_k,
            request_id=request_id,
            session_digest=session_digest,
            trace=trace,
        )
        if result.kind is not AnswerKind.ANSWERED:
            return result
        context = self._product_context(workspace_id)
        if context is None:
            return self._refusal(
                kind=AnswerKind.REFUSED_POLICY,
                request_id=request_id,
                workspace_id=workspace_id,
                reason_code="EXECUTION_AUTHORITY_UNAVAILABLE",
                pipeline=pipeline,
            )
        _pipeline, authority, _registered_session = context
        try:
            receipt = authority.issue(
                request_id=request_id,
                session_digest=session_digest,
                action="ask",
                workspace_id=workspace_id,
                generation_id=pipeline.index.manifest.generation_id,
                answer_sha256=sha256_bytes(result.answer.encode("utf-8")),
            )
        except (ExecutionAuthorityError, Helper1ContractError):
            return self._refusal(
                kind=AnswerKind.REFUSED_POLICY,
                request_id=request_id,
                workspace_id=workspace_id,
                reason_code="EXECUTION_RECEIPT_NOT_ATTESTED",
                pipeline=pipeline,
            )
        return replace(result, execution_receipt=receipt.to_dict())

    def search(
        self,
        *,
        workspace_id: str,
        query: str,
        top_k: int,
        request_id: str,
        client_request_id: str,
        requested_generation_id: str | None,
        effect_intent: str,
        session_digest: str,
    ) -> tuple[int, dict[str, Any]]:
        pipeline, refusal = self._authorize_request(
            workspace_id=workspace_id,
            request_id=request_id,
            client_request_id=client_request_id,
            requested_generation_id=requested_generation_id,
            effect_intent=effect_intent,
            session_digest=session_digest,
        )
        if refusal is not None:
            return refusal.http_status, refusal.to_public_dict()
        assert pipeline is not None
        trace = self._start_trace(
            pipeline=pipeline,
            request_id=request_id,
            workspace_id=workspace_id,
            session_digest=session_digest,
            action="search",
            input_chars=len(query),
            top_k=top_k,
            effect_intent=effect_intent,
        )
        try:
            chunks, observation = pipeline.observed_search(
                query=query,
                top_k=top_k,
                request_id=request_id,
                session_digest=session_digest,
            )
        except MeasurementError:
            trace.terminal(AnswerKind.REFUSED_MEASUREMENT_INVALID.value)
            trace.verify_complete()
            refusal = self._refusal(
                kind=AnswerKind.REFUSED_MEASUREMENT_INVALID,
                request_id=request_id,
                workspace_id=workspace_id,
                reason_code="MEASUREMENT_INVALID",
                pipeline=pipeline,
            )
            return refusal.http_status, refusal.to_public_dict()
        except Exception:
            trace.terminal(AnswerKind.REFUSED_INDEX_INVALID.value)
            trace.verify_complete()
            refusal = self._refusal(
                kind=AnswerKind.REFUSED_INDEX_INVALID,
                request_id=request_id,
                workspace_id=workspace_id,
                reason_code="INDEX_OR_EMBEDDING_INVALID",
                pipeline=pipeline,
            )
            return refusal.http_status, refusal.to_public_dict()
        self._append_observed_operation(
            trace=trace,
            operation_metadata={
                "count": len(chunks),
                "retrieval_policy_sha256": pipeline.retriever.policy.digest,
            },
            content_metadata={
                "generation_id": pipeline.index.manifest.generation_id,
                "chunks_sha256": sha256_bytes(
                    canonical_json(
                        [
                            {
                                "chunk_id": chunk.chunk_id,
                                "content_sha256": chunk.content_sha256,
                            }
                            for chunk in chunks
                        ]
                    )
                ),
            },
            observation=observation,
        )
        context = self._product_context(workspace_id)
        if context is None:
            trace.terminal(AnswerKind.REFUSED_POLICY.value)
            trace.verify_complete()
            refusal = self._refusal(
                kind=AnswerKind.REFUSED_POLICY,
                request_id=request_id,
                workspace_id=workspace_id,
                reason_code="EXECUTION_AUTHORITY_UNAVAILABLE",
                pipeline=pipeline,
            )
            return refusal.http_status, refusal.to_public_dict()
        _pipeline, authority, _registered_session = context
        try:
            receipt = authority.issue(
                request_id=request_id,
                session_digest=session_digest,
                action="search",
                workspace_id=workspace_id,
                generation_id=pipeline.index.manifest.generation_id,
                answer_sha256=None,
            )
        except (ExecutionAuthorityError, Helper1ContractError):
            trace.terminal(AnswerKind.REFUSED_POLICY.value)
            trace.verify_complete()
            refusal = self._refusal(
                kind=AnswerKind.REFUSED_POLICY,
                request_id=request_id,
                workspace_id=workspace_id,
                reason_code="EXECUTION_RECEIPT_NOT_ATTESTED",
                pipeline=pipeline,
            )
            return refusal.http_status, refusal.to_public_dict()
        trace.terminal("SEARCHED")
        trace.verify_complete()
        return 200, {
            "schema_version": "butler.helper1.search.v2",
            "kind": "SEARCHED",
            "request_id": request_id,
            "workspace_id": workspace_id,
            "generation_id": pipeline.index.manifest.generation_id,
            "index_manifest_sha256": pipeline.index.manifest.digest,
            "execution_receipt": receipt.to_dict(),
            "egress_observation": asdict(observation),
            "trace_root_sha256": trace.root,
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

    def index(
        self,
        *,
        workspace_id: str,
        request_id: str,
        client_request_id: str,
        requested_generation_id: str | None,
        effect_intent: str,
        session_digest: str,
    ) -> tuple[int, dict[str, Any]]:
        pipeline, refusal = self._authorize_request(
            workspace_id=workspace_id,
            request_id=request_id,
            client_request_id=client_request_id,
            requested_generation_id=requested_generation_id,
            effect_intent=effect_intent,
            session_digest=session_digest,
            expected_effect_intent="index_only",
        )
        if refusal is not None:
            return refusal.http_status, refusal.to_public_dict()
        assert pipeline is not None
        if type(pipeline.index_operation) is not NativeIndexOperation:
            refusal = self._refusal(
                kind=AnswerKind.REFUSED_ASSET_MISSING,
                request_id=request_id,
                workspace_id=workspace_id,
                reason_code="INDEX_AUTHORITY_UNAVAILABLE",
                pipeline=pipeline,
            )
            return refusal.http_status, refusal.to_public_dict()
        with self._lock:
            if workspace_id in self._pending_indexes:
                refusal = self._refusal(
                    kind=AnswerKind.REFUSED_POLICY,
                    request_id=request_id,
                    workspace_id=workspace_id,
                    reason_code="INDEX_CANDIDATE_ALREADY_PENDING",
                    pipeline=pipeline,
                )
                return refusal.http_status, refusal.to_public_dict()
        trace = self._start_trace(
            pipeline=pipeline,
            request_id=request_id,
            workspace_id=workspace_id,
            session_digest=session_digest,
            action="index",
            input_chars=0,
            top_k=None,
            effect_intent=effect_intent,
        )
        try:
            candidate, observation = pipeline.observed_index(
                workspace_id=workspace_id,
                request_id=request_id,
                session_digest=session_digest,
            )
        except MeasurementError:
            trace.terminal(AnswerKind.REFUSED_MEASUREMENT_INVALID.value)
            trace.verify_complete()
            refusal = self._refusal(
                kind=AnswerKind.REFUSED_MEASUREMENT_INVALID,
                request_id=request_id,
                workspace_id=workspace_id,
                reason_code="MEASUREMENT_INVALID",
                pipeline=pipeline,
            )
            return refusal.http_status, refusal.to_public_dict()
        except Exception:
            trace.terminal(AnswerKind.REFUSED_INDEX_INVALID.value)
            trace.verify_complete()
            refusal = self._refusal(
                kind=AnswerKind.REFUSED_INDEX_INVALID,
                request_id=request_id,
                workspace_id=workspace_id,
                reason_code="INDEX_BUILD_FAILED",
                pipeline=pipeline,
            )
            return refusal.http_status, refusal.to_public_dict()
        with self._lock:
            current = self._pipelines.get(workspace_id)
            if (
                current is not pipeline
                or workspace_id in self._pending_indexes
                or candidate.manifest.previous_generation_id
                != pipeline.index.manifest.generation_id
            ):
                trace.terminal(AnswerKind.REFUSED_POLICY.value)
                trace.verify_complete()
                refusal = self._refusal(
                    kind=AnswerKind.REFUSED_POLICY,
                    request_id=request_id,
                    workspace_id=workspace_id,
                    reason_code="INDEX_CANDIDATE_STALE",
                    pipeline=pipeline,
                )
                return refusal.http_status, refusal.to_public_dict()
            self._pending_indexes[workspace_id] = candidate
        self._append_observed_operation(
            trace=trace,
            operation_metadata={
                "status": "INDEX_CANDIDATE_BUILT",
                "candidate_generation_id": candidate.manifest.generation_id,
            },
            content_metadata={
                "candidate_manifest_sha256": candidate.manifest.digest,
                "previous_generation_id": candidate.manifest.previous_generation_id,
            },
            observation=observation,
        )
        trace.terminal("INDEXED_PENDING_ACTIVATION")
        trace.verify_complete()
        return 202, {
            "schema_version": "butler.helper1.index-result.v2",
            "kind": "INDEXED_PENDING_ACTIVATION",
            "request_id": request_id,
            "workspace_id": workspace_id,
            "previous_generation_id": pipeline.index.manifest.generation_id,
            "candidate_generation_id": candidate.manifest.generation_id,
            "candidate_manifest_sha256": candidate.manifest.digest,
            "egress_observation": asdict(observation),
            "trace_root_sha256": trace.root,
        }


_SERVICE = Helper1Service()


def get_helper1_service() -> Helper1Service:
    return _SERVICE
