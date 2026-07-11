from __future__ import annotations

import queue
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Mapping

from .box_policies import classify_cascade_reason, phase0_policies
from .capability_registry import CapabilityRegistry, phase0_default_registry
from .cascade_policy import plan_shadow_cascade
from .contracts import GateResult, ProfileValidity, stable_digest
from .device_profiler import DeviceProfileSampler, unknown_device_profile
from .routing_audit import HashChainJsonlWriter, build_shadow_record, default_shadow_audit_path
from .runtime_state import RuntimeStateMonitor
from .task_profiler import classify_task_complexity
from .tier_router import route_tier


@dataclass(frozen=True)
class ShadowRecorderStats:
    submitted: int
    written: int
    dropped: int
    failures: int


class NonBlockingShadowRecorder:
    """Bounded, daemon-backed audit writer that never blocks product requests."""

    def __init__(
        self,
        writer: HashChainJsonlWriter,
        *,
        queue_capacity: int = 256,
    ) -> None:
        if queue_capacity <= 0:
            raise ValueError("SHADOW_QUEUE_CAPACITY_INVALID")
        self._writer = writer
        self._queue: queue.Queue[dict[str, Any] | None] = queue.Queue(queue_capacity)
        self._lock = threading.Lock()
        self._submitted = 0
        self._written = 0
        self._dropped = 0
        self._failures = 0
        self._closed = False
        self._thread = threading.Thread(
            target=self._run,
            name="butler-model-tier-audit",
            daemon=True,
        )
        self._thread.start()

    def submit(self, record: dict[str, Any]) -> bool:
        with self._lock:
            if self._closed:
                self._dropped += 1
                return False
            self._submitted += 1
        try:
            self._queue.put_nowait(dict(record))
            return True
        except queue.Full:
            with self._lock:
                self._dropped += 1
            return False

    def stats(self) -> ShadowRecorderStats:
        with self._lock:
            return ShadowRecorderStats(
                submitted=self._submitted,
                written=self._written,
                dropped=self._dropped,
                failures=self._failures,
            )

    def close(self, *, timeout_seconds: float = 1.0) -> None:
        with self._lock:
            if self._closed:
                return
            self._closed = True
        deadline = time.monotonic() + max(0.0, timeout_seconds)
        while True:
            try:
                self._queue.put(None, timeout=max(0.0, min(0.05, deadline - time.monotonic())))
                break
            except queue.Full:
                if time.monotonic() >= deadline:
                    return
        self._thread.join(max(0.0, deadline - time.monotonic()))

    def _run(self) -> None:
        while True:
            record = self._queue.get()
            try:
                if record is None:
                    return
                self._writer.append(record)
                with self._lock:
                    self._written += 1
            except Exception:
                with self._lock:
                    self._failures += 1
            finally:
                self._queue.task_done()


def observe_best_effort(
    record_factory: Callable[[], dict[str, Any]],
    recorder: NonBlockingShadowRecorder,
) -> None:
    try:
        recorder.submit(record_factory())
    except Exception:
        return


def response_digest_best_effort(value: Any) -> str:
    try:
        return stable_digest(value)
    except Exception:
        return stable_digest({"response_digest": "unavailable"})


class Phase0ShadowObserver:
    def __init__(
        self,
        *,
        registry: CapabilityRegistry,
        runtime_monitor: RuntimeStateMonitor,
        device_sampler: DeviceProfileSampler,
        recorder: NonBlockingShadowRecorder,
    ) -> None:
        self._registry = registry
        self._runtime_monitor = runtime_monitor
        self._device_sampler = device_sampler
        self._recorder = recorder
        self._policies = phase0_policies()

    def close(self) -> None:
        self._recorder.close()

    def observe_box1(
        self,
        *,
        request_digest: str,
        actual_response_digest: str,
        facts: Mapping[str, Any],
    ) -> None:
        self._observe(
            box_id="1",
            request_digest=request_digest,
            actual_response_digest=actual_response_digest,
            facts=facts,
            gate=None,
        )

    def observe_box3(
        self,
        *,
        request_digest: str,
        actual_response_digest: str,
        facts: Mapping[str, Any],
        fail_class: str | None,
        quality_vector: Mapping[str, float | int | bool] | None = None,
    ) -> None:
        severity = classify_cascade_reason(fail_class)
        gate_payload = {
            "passed": not fail_class,
            "reason_code": fail_class,
            "severity": severity,
            "quality_vector": dict(quality_vector or {}),
        }
        gate = GateResult(
            schema_version="butler.gate_result.v1",
            passed=not fail_class,
            reason_code=fail_class,
            severity=severity,
            quality_vector=dict(quality_vector or {}),
            result_digest=stable_digest(gate_payload),
        )
        self._observe(
            box_id="3",
            request_digest=request_digest,
            actual_response_digest=actual_response_digest,
            facts=facts,
            gate=gate,
        )

    def _observe(
        self,
        *,
        box_id: str,
        request_digest: str,
        actual_response_digest: str,
        facts: Mapping[str, Any],
        gate: GateResult | None,
    ) -> None:
        task = classify_task_complexity(box_id, facts)
        device = self._device_sampler.latest()
        if device.validity is ProfileValidity.INVALID:
            device = unknown_device_profile("DEVICE_PROFILE_INVALID")
        policy = self._policies[box_id]
        decision = route_tier(
            task=task,
            device=device,
            policy=policy,
            registry=self._registry,
            runtime_states=self._runtime_monitor.snapshot(),
        )
        gate_reason: str | None = None
        would_escalate = False
        if gate is not None:
            plan = plan_shadow_cascade(
                box_id=box_id,
                gate=gate,
                policy=policy,
                high_eligible=decision.high_eligible,
            )
            gate_reason = gate.reason_code
            would_escalate = plan.would_escalate
        observe_best_effort(
            lambda: build_shadow_record(
                timestamp_epoch_ms=int(time.time() * 1000),
                request_digest=request_digest,
                box_id=box_id,
                task_profile_digest=task.task_digest,
                device_profile_digest=device.profile_digest,
                policy_digest=policy.policy_digest,
                decision_digest=decision.decision_digest,
                recommended_tier=decision.recommended_tier.value,
                recommended_variant_id=decision.recommended_variant_id,
                reason_codes=decision.reason_codes,
                high_eligible=decision.high_eligible,
                gate_reason_code=gate_reason,
                would_escalate=would_escalate,
                actual_response_digest=actual_response_digest,
            ),
            self._recorder,
        )


_GLOBAL_LOCK = threading.Lock()
_GLOBAL_OBSERVER: Phase0ShadowObserver | None = None


def initialize_phase0_shadow(
    *,
    runtime_monitor: RuntimeStateMonitor,
    device_sampler: DeviceProfileSampler,
    audit_path: Path | None = None,
) -> Phase0ShadowObserver | None:
    """Initialize best effort; product startup must never depend on Phase 0."""
    global _GLOBAL_OBSERVER
    try:
        observer = Phase0ShadowObserver(
            registry=phase0_default_registry(),
            runtime_monitor=runtime_monitor,
            device_sampler=device_sampler,
            recorder=NonBlockingShadowRecorder(
                HashChainJsonlWriter(audit_path or default_shadow_audit_path())
            ),
        )
    except Exception:
        return None
    with _GLOBAL_LOCK:
        previous = _GLOBAL_OBSERVER
        _GLOBAL_OBSERVER = observer
    if previous is not None:
        previous.close()
    return observer


def shutdown_phase0_shadow() -> None:
    global _GLOBAL_OBSERVER
    with _GLOBAL_LOCK:
        observer = _GLOBAL_OBSERVER
        _GLOBAL_OBSERVER = None
    if observer is not None:
        observer.close()


def observe_box1_best_effort(**kwargs: Any) -> None:
    with _GLOBAL_LOCK:
        observer = _GLOBAL_OBSERVER
    if observer is None:
        return
    try:
        observer.observe_box1(**kwargs)
    except Exception:
        return


def observe_box3_best_effort(**kwargs: Any) -> None:
    with _GLOBAL_LOCK:
        observer = _GLOBAL_OBSERVER
    if observer is None:
        return
    try:
        observer.observe_box3(**kwargs)
    except Exception:
        return
