from __future__ import annotations

import asyncio
import hashlib
import json
import os
import statistics
import time
from dataclasses import FrozenInstanceError
from pathlib import Path
from types import SimpleNamespace

import pytest

from butler_pc_core.connect_loop.box1_router import canonical_sha256
from butler_pc_core.model_tier.capability_registry import phase0_default_registry
from butler_pc_core.model_tier.contracts import sha256_text
from butler_pc_core.model_tier.device_profiler import collect_device_profile
from butler_pc_core.model_tier.routing_audit import HashChainJsonlWriter
from butler_pc_core.model_tier.live_evidence import validate_live_shadow_evidence
from butler_pc_core.model_tier.runtime_state import (
    RuntimeProbe,
    RuntimeStateMonitor,
    publish_runtime_lifecycle,
    runtime_lifecycle_snapshot,
)
from butler_pc_core.model_tier.shadow_observer import Phase0ShadowObserver
from butler_pc_core.sidecar.routes import box3_draft, router_decide


def _request() -> SimpleNamespace:
    return SimpleNamespace(
        client=SimpleNamespace(host="testclient"),
        state=SimpleNamespace(policy_gate_allowed=True),
        headers={},
    )


def _box1_payload() -> router_decide.RouterDecidePayload:
    runtime_text = "지난달 회의 기록을 찾아줘"
    return router_decide.RouterDecidePayload(
        chat_request={
            "schema_version": "chat_request.v1",
            "request_id": "req-p0-hardening-001",
            "session_id_digest": canonical_sha256("session"),
            "tenant_id_digest": canonical_sha256("tenant"),
            "device_id": "device-local-test",
            "user_role": "employee",
            "department_id_digest": canonical_sha256("department"),
            "text_ref": "device_local_only",
            "text_digest": canonical_sha256(runtime_text),
            "attachments": [],
            "created_at": "2026-07-12T00:00:00Z",
        },
        runtime={"runtime_text": runtime_text},
    )


def _audit_record(index: int) -> dict:
    from butler_pc_core.model_tier.routing_audit import build_shadow_record

    digest = sha256_text(str(index))
    return build_shadow_record(
        timestamp_epoch_ms=index,
        request_digest=digest,
        box_id="3",
        task_profile_digest=digest,
        device_profile_digest=digest,
        policy_digest=digest,
        decision_digest=digest,
        recommended_tier="TIER_1P7B",
        recommended_variant_id="box3_v9_2_r2b_1p7_q4_k_m",
        reason_codes=("BOX3_SPECIALIZED_1P7B_PRIMARY",),
        high_eligible=False,
        gate_reason_code=None,
        would_escalate=False,
        actual_response_digest=digest,
    )


def test_pre_context_created_before_box1_product_boundary(monkeypatch) -> None:
    order: list[str] = []
    original_decide = router_decide.RuleBasedBox1Router.decide

    def product(self, *args, **kwargs):
        order.append("product")
        return original_decide(self, *args, **kwargs)

    monkeypatch.setattr(router_decide.RuleBasedBox1Router, "decide", product)
    monkeypatch.setattr(
        router_decide,
        "prepare_box1_shadow_best_effort",
        lambda **_kwargs: order.append("pre") or object(),
    )
    monkeypatch.setattr(
        router_decide,
        "complete_box1_shadow_best_effort",
        lambda **_kwargs: order.append("post"),
    )
    asyncio.run(router_decide.decide_router(_box1_payload(), _request()))
    assert order == ["pre", "product", "post"]


def test_pre_context_created_before_box3_product_boundary(monkeypatch) -> None:
    order: list[str] = []
    fixed = {"status": "real_candidate", "fail_class": None, "draft_text": "초안", "citations": []}
    monkeypatch.setattr(
        box3_draft,
        "prepare_box3_shadow_best_effort",
        lambda **_kwargs: order.append("pre") or object(),
    )
    monkeypatch.setattr(
        box3_draft,
        "run_box3_endpoint_wiring",
        lambda **_kwargs: order.append("product") or dict(fixed),
    )
    monkeypatch.setattr(
        box3_draft,
        "complete_box3_shadow_best_effort",
        lambda **_kwargs: order.append("post"),
    )
    payload = box3_draft.Box3DraftRequest(reference_docs=["참고"], drafting_request="작성")
    asyncio.run(box3_draft.draft_box3(payload, _request()))
    assert order == ["pre", "product", "post"]


def test_box3_live_request_id_is_forwarded_only_when_safe(monkeypatch) -> None:
    seen: list[str | None] = []
    monkeypatch.setattr(box3_draft, "prepare_box3_shadow_best_effort", lambda **_kwargs: None)
    monkeypatch.setattr(box3_draft, "complete_box3_shadow_best_effort", lambda **_kwargs: None)
    monkeypatch.setattr(
        box3_draft,
        "run_box3_endpoint_wiring",
        lambda **kwargs: seen.append(kwargs.get("request_id"))
        or {"status": "real_candidate", "draft_text": "초안", "citations": []},
    )
    payload = box3_draft.Box3DraftRequest(reference_docs=["참고"], drafting_request="작성")
    safe_request = _request()
    safe_request.headers = {"x-request-id": "phase0-live-box3-pass-001"}
    asyncio.run(box3_draft.draft_box3(payload, safe_request))
    unsafe_request = _request()
    unsafe_request.headers = {"x-request-id": "raw text is forbidden"}
    asyncio.run(box3_draft.draft_box3(payload, unsafe_request))
    assert seen == ["phase0-live-box3-pass-001", None]


@pytest.mark.parametrize("failing_hook", ["pre", "post"])
def test_box1_hook_failure_keeps_response_bytes(monkeypatch, failing_hook: str) -> None:
    monkeypatch.setattr(router_decide, "prepare_box1_shadow_best_effort", lambda **_kwargs: None)
    monkeypatch.setattr(router_decide, "complete_box1_shadow_best_effort", lambda **_kwargs: None)
    baseline = asyncio.run(router_decide.decide_router(_box1_payload(), _request()))

    def fail(**_kwargs):
        raise RuntimeError("synthetic hook failure")

    target = "prepare_box1_shadow_best_effort" if failing_hook == "pre" else "complete_box1_shadow_best_effort"
    monkeypatch.setattr(router_decide, target, fail)
    observed = asyncio.run(router_decide.decide_router(_box1_payload(), _request()))
    assert json.dumps(observed, sort_keys=True) == json.dumps(baseline, sort_keys=True)


def test_shadow_pre_context_is_frozen_and_digest_only() -> None:
    profile = collect_device_profile(
        {
            "total_memory_bytes": 64 * 1024**3,
            "available_memory_bytes": 32 * 1024**3,
            "process_rss_bytes": 1024,
            "memory_pressure": "NORMAL",
            "thermal_state": "NOMINAL",
            "low_power_mode": False,
            "battery_percent": 90,
            "metal_available": True,
            "chip_family": "Apple M3 Max",
        }
    )
    recorder = SimpleNamespace(submit=lambda _record: True, close=lambda: None)
    observer = Phase0ShadowObserver(
        registry=phase0_default_registry(),
        runtime_monitor=SimpleNamespace(snapshot=lambda: {}),
        device_sampler=SimpleNamespace(latest=lambda: profile),
        recorder=recorder,
    )
    digest = sha256_text("request")
    context = observer.prepare_box1(
        request_digest=digest,
        facts={"payload_digest": digest, "input_chars": 10},
    )
    assert "runtime_text" not in vars(context)
    assert all("sha256:" in value for key, value in vars(context).items() if key.endswith("_digest"))
    with pytest.raises(FrozenInstanceError):
        context.box_id = "3"  # type: ignore[misc]


def test_box3_path_exists_but_is_not_resident(tmp_path: Path) -> None:
    model = tmp_path / "box3.gguf"
    model.write_bytes(b"synthetic-model")
    monitor = RuntimeStateMonitor(
        lambda: (
            RuntimeProbe(
                variant_id="box3-test",
                model_path=str(model),
                loaded=False,
                ready=False,
            ),
        )
    )
    state = monitor.sample_once()["box3-test"]
    assert state.asset_available is True
    assert state.loaded is False
    assert state.ready is False
    assert state.resident is False


def test_lifecycle_publisher_is_required_for_loaded_ready() -> None:
    variant_id = "box3-lifecycle-test"
    publish_runtime_lifecycle(
        variant_id,
        model_path="/models/box3.gguf",
        loaded=True,
        ready=True,
        process_id=os.getpid(),
    )
    state = runtime_lifecycle_snapshot()[variant_id]
    assert state.loaded is True and state.ready is True


def test_same_size_mtime_swap_rehashed(tmp_path: Path) -> None:
    model = tmp_path / "model.gguf"
    model.write_bytes(b"AAAA")
    original_mtime = model.stat().st_mtime_ns
    monitor = RuntimeStateMonitor(
        lambda: (RuntimeProbe("swap-test", str(model), False, False),)
    )
    first = monitor.sample_once()["swap-test"].model_digest
    replacement = tmp_path / "replacement.gguf"
    replacement.write_bytes(b"BBBB")
    os.utime(replacement, ns=(original_mtime, original_mtime))
    os.replace(replacement, model)
    os.utime(model, ns=(original_mtime, original_mtime))
    second = monitor.sample_once()["swap-test"].model_digest
    assert first == "sha256:" + hashlib.sha256(b"AAAA").hexdigest()
    assert second == "sha256:" + hashlib.sha256(b"BBBB").hexdigest()
    assert second != first


def test_model_digest_rejects_symlink(tmp_path: Path) -> None:
    real = tmp_path / "real.gguf"
    real.write_bytes(b"model")
    link = tmp_path / "link.gguf"
    link.symlink_to(real)
    monitor = RuntimeStateMonitor(
        lambda: (RuntimeProbe("link-test", str(link), False, False),)
    )
    state = monitor.sample_once()["link-test"]
    assert state.asset_available is False
    assert state.model_digest is None


@pytest.mark.parametrize("crash_state", ["missing", "empty", "partial", "valid_then_partial"])
def test_rotation_crash_recovers_without_chain_reset(tmp_path: Path, crash_state: str) -> None:
    path = tmp_path / "audit" / "shadow.jsonl"
    writer = HashChainJsonlWriter(path)
    first_digest = writer.append(_audit_record(1))
    rotated = path.with_name(path.name + ".1")
    os.replace(path, rotated)

    expected_previous = first_digest
    if crash_state == "empty":
        path.write_bytes(b"")
    elif crash_state == "partial":
        path.write_bytes(b'{"partial":')
    elif crash_state == "valid_then_partial":
        writer2 = HashChainJsonlWriter(path)
        expected_previous = writer2.append(_audit_record(2))
        with path.open("ab") as handle:
            handle.write(b'{"partial":')

    recovered = HashChainJsonlWriter(path)
    recovered.append(_audit_record(3))
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    assert rows[-1]["previous_record_digest"] == expected_previous
    assert rows[-1]["previous_record_digest"] != "sha256:" + "0" * 64


def test_hook_p95_under_5ms() -> None:
    profile = collect_device_profile(
        {
            "total_memory_bytes": 64 * 1024**3,
            "available_memory_bytes": 32 * 1024**3,
            "process_rss_bytes": 1024,
            "memory_pressure": "NORMAL",
            "thermal_state": "NOMINAL",
            "low_power_mode": False,
            "battery_percent": 90,
            "metal_available": True,
            "chip_family": "Apple M3 Max",
        }
    )
    recorder = SimpleNamespace(submit=lambda _record: True, close=lambda: None)
    observer = Phase0ShadowObserver(
        registry=phase0_default_registry(),
        runtime_monitor=SimpleNamespace(snapshot=lambda: {}),
        device_sampler=SimpleNamespace(latest=lambda: profile),
        recorder=recorder,
    )
    digest = sha256_text("request")
    durations: list[float] = []
    for _ in range(200):
        started = time.perf_counter_ns()
        context = observer.prepare_box1(
            request_digest=digest,
            facts={"payload_digest": digest, "input_chars": 10},
        )
        observer.complete_box1(pre_context=context, actual_response_digest=digest)
        durations.append((time.perf_counter_ns() - started) / 1_000_000)
    p95 = statistics.quantiles(durations, n=100, method="inclusive")[94]
    assert p95 < 5.0


def test_live_shadow_not_synthetic() -> None:
    digest = sha256_text("live")
    evidence = {
        "schema_version": "butler.model_tier_live_shadow_evidence.v1",
        "capture_source": "butler_app_live_http",
        "synthetic": False,
        "chip_family": "Apple M3 Max",
        "app_executable_digest": digest,
        "cases": [
            {
                "case_id": case_id,
                "hook_off_response_digest": digest,
                "hook_on_response_digest": digest,
            }
            for case_id in ("box1_simple", "box1_ambiguous", "box3_pass", "box3_review")
        ],
        "raw_key_findings": 0,
        "hook_on_counter_delta": {"submitted": 4, "written": 4, "dropped": 0, "failures": 0},
    }
    validate_live_shadow_evidence(evidence)
    evidence["synthetic"] = True
    with pytest.raises(ValueError, match="SYNTHETIC_FORBIDDEN"):
        validate_live_shadow_evidence(evidence)
