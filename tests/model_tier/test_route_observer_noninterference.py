from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace

from butler_pc_core.connect_loop.box1_router import canonical_sha256
from butler_pc_core.sidecar.routes import box3_draft, router_decide


def _request() -> SimpleNamespace:
    return SimpleNamespace(
        client=SimpleNamespace(host="testclient"),
        state=SimpleNamespace(policy_gate_allowed=True),
    )


def test_box1_response_bytes_unchanged_when_shadow_observer_runs(monkeypatch) -> None:
    runtime_text = "지난달 회의 기록을 찾아줘"
    payload = router_decide.RouterDecidePayload(
        chat_request={
            "schema_version": "chat_request.v1",
            "request_id": "req-12345678",
            "session_id_digest": canonical_sha256("session"),
            "tenant_id_digest": canonical_sha256("tenant"),
            "device_id": "device-local-test",
            "user_role": "employee",
            "department_id_digest": canonical_sha256("department"),
            "text_ref": "device_local_only",
            "text_digest": canonical_sha256(runtime_text),
            "attachments": [],
            "created_at": "2026-07-11T00:00:00Z",
        },
        runtime={"runtime_text": runtime_text},
    )
    monkeypatch.setattr(router_decide, "prepare_box1_shadow_best_effort", lambda **_kwargs: None)
    monkeypatch.setattr(router_decide, "complete_box1_shadow_best_effort", lambda **_kwargs: None)
    baseline = asyncio.run(router_decide.decide_router(payload, _request()))
    seen = []
    sentinel = object()
    monkeypatch.setattr(
        router_decide,
        "prepare_box1_shadow_best_effort",
        lambda **kwargs: seen.append(("pre", kwargs)) or sentinel,
    )
    monkeypatch.setattr(
        router_decide,
        "complete_box1_shadow_best_effort",
        lambda **kwargs: seen.append(("post", kwargs)),
    )
    observed = asyncio.run(router_decide.decide_router(payload, _request()))
    assert json.dumps(observed, sort_keys=True) == json.dumps(baseline, sort_keys=True)
    assert [stage for stage, _ in seen] == ["pre", "post"]
    assert "runtime_text" not in seen[0][1]
    assert seen[1][1]["pre_context"] is sentinel


def test_box3_response_bytes_unchanged_when_shadow_observer_runs(monkeypatch) -> None:
    fixed = {
        "status": "real_candidate",
        "fail_class": "FIXED_EVAL_PENDING",
        "draft_text": "합성 초안",
        "citations": [],
        "needs_review": True,
    }
    monkeypatch.setattr(box3_draft, "run_box3_endpoint_wiring", lambda **_kwargs: dict(fixed))
    payload = box3_draft.Box3DraftRequest(
        reference_docs=["합성 참고문서"],
        drafting_request="합성 초안을 작성해줘",
    )
    monkeypatch.setattr(box3_draft, "prepare_box3_shadow_best_effort", lambda **_kwargs: None)
    monkeypatch.setattr(box3_draft, "complete_box3_shadow_best_effort", lambda **_kwargs: None)
    baseline = asyncio.run(box3_draft.draft_box3(payload, _request()))
    seen = []
    sentinel = object()
    monkeypatch.setattr(
        box3_draft,
        "prepare_box3_shadow_best_effort",
        lambda **kwargs: seen.append(("pre", kwargs)) or sentinel,
    )
    monkeypatch.setattr(
        box3_draft,
        "complete_box3_shadow_best_effort",
        lambda **kwargs: seen.append(("post", kwargs)),
    )
    observed = asyncio.run(box3_draft.draft_box3(payload, _request()))
    assert json.dumps(observed, ensure_ascii=False, sort_keys=True) == json.dumps(
        baseline,
        ensure_ascii=False,
        sort_keys=True,
    )
    assert [stage for stage, _ in seen] == ["pre", "post"]
    assert "reference_docs" not in seen[0][1]
    assert "draft_text" not in seen[1][1]
    assert seen[1][1]["pre_context"] is sentinel
