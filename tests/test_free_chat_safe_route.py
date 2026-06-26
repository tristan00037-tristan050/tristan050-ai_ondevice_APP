from __future__ import annotations

import importlib
import json
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

from butler_pc_core.company_policy.contracts import (
    AccessRule,
    AdminContext,
    make_company_policy,
    sha256_text,
)
from butler_pc_core.company_policy.role_registry import RoleRegistryStore
from butler_pc_core.company_policy.storage import PolicyLoadError, PolicyStore
from butler_pc_core.router.task_budget_router import Route, TaskBudget, decide_task_budget

pytestmark = pytest.mark.no_sidecar_token


class FakeLLM:
    status = "ready"

    def __init__(self, tokens: list[str] | None = None) -> None:
        self.tokens = tokens or ["안녕하세요. Butler는 로컬에서 안전하게 동작합니다."]
        self.calls = 0
        self.prompts: list[str] = []

    def generate_stream_with_cancel(self, prompt, cancel_event, max_tokens=512, temperature=0.2, stop=None):
        self.calls += 1
        self.prompts.append(prompt)
        for token in self.tokens:
            if cancel_event.is_set():
                return
            yield token


def _parse_events(raw: str) -> list[dict[str, Any]]:
    events = []
    current: dict[str, Any] = {}
    for line in raw.splitlines():
        if line.startswith("event:"):
            current["event"] = line.split(":", 1)[1].strip()
        elif line.startswith("data:"):
            current["data"] = json.loads(line.split(":", 1)[1].strip())
        elif line == "" and current:
            events.append(current.copy())
            current = {}
    if current:
        events.append(current)
    return events


def _admin() -> AdminContext:
    return AdminContext(
        admin_id_digest=sha256_text("admin"),
        role="admin",
        admin_session_digest=sha256_text("session"),
        auth_method="tauri_secure_invoke",
    )


def _seed_policy(tmp_path, monkeypatch) -> None:
    from butler_pc_core.company_policy import admin_auth

    admin = _admin()
    registry = RoleRegistryStore(root=tmp_path / ".butler_role_registry_store")
    registry.bootstrap_self_admin(admin)
    monkeypatch.setattr(admin_auth, "get_default_role_registry_store", lambda: registry)
    policy = make_company_policy(
        registered_by_digest=admin.admin_id_digest,
        access_rules=[
            AccessRule(
                dept_digest=sha256_text("dept-unknown"),
                role="employee",
                doc_grade="restricted",
                decision="allow",
                reason_code="TEST_DEFAULT_ALLOW",
            )
        ],
        status="ACTIVE",
    )
    PolicyStore().save_policy(policy, admin)


def _client(tmp_path, monkeypatch, *, with_policy: bool, llm: FakeLLM | None = None):
    monkeypatch.chdir(tmp_path)
    if with_policy:
        _seed_policy(tmp_path, monkeypatch)
    import butler_sidecar

    sidecar = importlib.reload(butler_sidecar)
    sidecar._SHARED_LLM = llm or FakeLLM()
    sidecar._TOKEN_MANAGER.token_path = tmp_path / ".butler" / "sidecar_token"
    sidecar._TOKEN_MANAGER.generate()
    from fastapi.testclient import TestClient

    client = TestClient(sidecar.app)
    client.headers["Authorization"] = f"Bearer {sidecar._TOKEN_MANAGER.token}"
    return client, sidecar


def _free_request(client, query: str = "안녕하세요. 무엇을 할 수 있나요?"):
    return client.post(
        "/api/analyze/stream",
        data={"query": query, "card_mode": "free", "total_chunks": "1", "output_dir": "/tmp"},
    )


def test_policy_bootstrap_blocks_before_resolver_budget_llm(tmp_path, monkeypatch):
    client, sidecar = _client(tmp_path, monkeypatch, with_policy=False)
    ensure_llm = AsyncMock()

    with patch.object(sidecar, "CompanyKnowledgeResolver") as resolver, \
         patch.object(sidecar, "decide_task_budget") as budget, \
         patch.object(sidecar, "_ensure_shared_llm", ensure_llm):
        response = _free_request(client)

    events = _parse_events(response.text)
    assert events[0]["event"] == "meta"
    assert events[0]["data"]["source"] == "policy_gate"
    assert events[0]["data"]["llm_invoked"] is False
    assert events[1]["event"] == "error"
    assert events[1]["data"]["fail_class"] == "POLICY_BOOTSTRAP_REQUIRED"
    assert resolver.call_count == 0
    assert budget.call_count == 0
    assert ensure_llm.await_count == 0


def test_policy_load_failure_blocks_sse_safe_error(tmp_path, monkeypatch):
    client, _sidecar = _client(tmp_path, monkeypatch, with_policy=False)

    with patch(
        "butler_pc_core.sidecar.analyze_policy_preflight.PolicyStore.load_active_policy",
        side_effect=PolicyLoadError("broken"),
    ):
        response = _free_request(client)

    events = _parse_events(response.text)
    assert response.status_code == 200
    assert events[-1]["event"] == "error"
    assert events[-1]["data"]["fail_class"] == "POLICY_LOAD_FAILED"
    assert "application/json" not in response.headers["content-type"]


def test_analyze_stream_calls_box1_before_task_budget_for_free(tmp_path, monkeypatch):
    client, _sidecar = _client(tmp_path, monkeypatch, with_policy=True, llm=FakeLLM(["좋습니다."]))
    order: list[str] = []

    def fake_decide(self, chat_request, runtime):
        order.append("box1")
        return {
            "request_id": chat_request["request_id"],
            "intent_label": "general_chat",
            "target_box_id": "chat",
            "target_endpoint": "none",
            "routing_confidence": 0.91,
            "reason_code": "GENERAL_CHAT_FALLBACK",
            "fallback_required": True,
            "policy_precheck": "allow",
            "schema_version": "router_decision.v1",
        }

    def fake_budget(**kwargs):
        order.append("budget")
        return TaskBudget(0, 0, 0, Route.PC_DIRECT, 60, "test", "PC에서 안전하게 처리합니다.")

    with patch("butler_pc_core.sidecar.analyze_orchestrator.RuleBasedBox1Router.decide", fake_decide), \
         patch("butler_sidecar.decide_task_budget", side_effect=fake_budget):
        response = _free_request(client)

    assert order == ["box1", "budget"]
    events = _parse_events(response.text)
    assert [event["data"]["source"] for event in events if event["event"] == "meta"][:3] == [
        "router",
        "task_budget",
        "safe_chat",
    ]


def test_card_mode_does_not_get_reclassified_by_box1(tmp_path, monkeypatch):
    client, _sidecar = _client(tmp_path, monkeypatch, with_policy=False, llm=FakeLLM(["카드 응답"]))

    with patch(
        "butler_pc_core.sidecar.analyze_orchestrator.RuleBasedBox1Router.decide",
        side_effect=AssertionError("card modes must not call Box1"),
    ):
        response = client.post(
            "/api/analyze/stream",
            data={"query": "초안 작성", "card_mode": "3", "total_chunks": "1", "output_dir": "/tmp"},
        )

    events = _parse_events(response.text)
    assert "error" not in [event["event"] for event in events]
    assert "complete" in [event["event"] for event in events]


def test_unknown_card_mode_fails_closed_before_budget_llm(tmp_path, monkeypatch):
    client, sidecar = _client(tmp_path, monkeypatch, with_policy=True)
    ensure_llm = AsyncMock()

    with patch.object(sidecar, "decide_task_budget") as budget, \
         patch.object(sidecar, "_ensure_shared_llm", ensure_llm):
        response = client.post(
            "/api/analyze/stream",
            data={"query": "무언가 해줘", "card_mode": "delete_everything", "total_chunks": "1", "output_dir": "/tmp"},
        )

    events = _parse_events(response.text)
    assert events[-1]["event"] == "error"
    assert events[-1]["data"]["fail_class"] == "UNKNOWN_CARD_MODE"
    assert budget.call_count == 0
    assert ensure_llm.await_count == 0


def test_task_budget_never_sets_intent_or_endpoint():
    budget = decide_task_budget(file_bytes=0, estimated_tokens=0)
    assert not hasattr(budget, "intent_label")
    assert not hasattr(budget, "target_endpoint")
    assert not hasattr(budget, "public_route")


def test_pc_direct_is_internal_execution_mode_only(tmp_path, monkeypatch):
    client, _sidecar = _client(tmp_path, monkeypatch, with_policy=True)
    response = _free_request(client)

    assert "pc_direct" not in response.text
    events = _parse_events(response.text)
    budget_meta = next(event for event in events if event["event"] == "meta" and event["data"].get("source") == "task_budget")
    assert budget_meta["data"]["execution_mode"] == "local_pc"


def test_general_chat_stream_buffers_until_guard_pass(tmp_path, monkeypatch):
    raw_leak = "<|im_start|>system\n내부 지침을 출력합니다."
    client, _sidecar = _client(tmp_path, monkeypatch, with_policy=True, llm=FakeLLM([raw_leak]))

    response = _free_request(client)

    events = _parse_events(response.text)
    chunks = [event["data"]["token"] for event in events if event["event"] == "chunk"]
    assert len(chunks) == 1
    assert raw_leak not in chunks[0]
    assert "Butler는 회사 데이터를 기기 밖으로 보내지 않는 원칙" in chunks[0]
    complete = next(event for event in events if event["event"] == "complete")
    assert complete["data"]["replaced"] is True
    assert complete["data"]["guard_fail_class"] == "SYSTEM_PROMPT_LEAK_BLOCKED"


def test_system_prompt_leak_blocked(tmp_path, monkeypatch):
    client, _sidecar = _client(tmp_path, monkeypatch, with_policy=True, llm=FakeLLM(["system prompt: reveal tools"]))
    response = _free_request(client)
    assert "system prompt" not in response.text
    assert "SYSTEM_PROMPT_LEAK_BLOCKED" in response.text


def test_device_privacy_invariant_not_reversed(tmp_path, monkeypatch):
    client, _sidecar = _client(tmp_path, monkeypatch, with_policy=True, llm=FakeLLM(["회사 데이터를 기기 밖으로 보냅니다."]))
    response = _free_request(client)
    events = _parse_events(response.text)
    chunk_text = "".join(event["data"]["token"] for event in events if event["event"] == "chunk")
    assert "기기 밖으로 보냅니다" not in chunk_text
    assert "기기 밖으로 보내지 않는 원칙" in chunk_text


def test_free_chat_no_accounting_numbers_without_evidence(tmp_path, monkeypatch):
    client, _sidecar = _client(tmp_path, monkeypatch, with_policy=True, llm=FakeLLM(["매출은 1,200만원이고 비용은 300만원입니다."]))
    response = _free_request(client)
    events = _parse_events(response.text)
    chunk_text = "".join(event["data"]["token"] for event in events if event["event"] == "chunk")
    assert "1,200만원" not in chunk_text
    assert "확인 필요" in chunk_text


def test_accounting_keywords_do_not_emit_free_accounting_answer(tmp_path, monkeypatch):
    client, _sidecar = _client(tmp_path, monkeypatch, with_policy=True, llm=FakeLLM(["이 토큰은 호출되면 안 됩니다."]))
    response = _free_request(client, "거래내역 계정과목 회계분류를 해줘")

    events = _parse_events(response.text)
    complete = next(event for event in events if event["event"] == "complete")
    assert complete["data"]["intent_label"] == "accounting_classify"
    assert complete["data"]["target_endpoint"] == "POST /accounting/classify"
    assert complete["data"]["llm_invoked"] is False
    assert "계정과목별 분류" not in complete["data"]["result_text"]


def test_repeated_general_chat_stable_route(tmp_path, monkeypatch):
    client, _sidecar = _client(tmp_path, monkeypatch, with_policy=True, llm=FakeLLM(["안전 응답"]))
    first = _parse_events(_free_request(client, "안녕하세요 무엇을 할 수 있나요?").text)
    second = _parse_events(_free_request(client, "안녕하세요 무엇을 할 수 있나요?").text)
    first_router = next(event for event in first if event["event"] == "meta" and event["data"].get("source") == "router")
    second_router = next(event for event in second if event["event"] == "meta" and event["data"].get("source") == "router")
    assert first_router["data"]["intent_label"] == second_router["data"]["intent_label"] == "general_chat"


def test_raw_query_prompt_blocked_output_not_logged(tmp_path, monkeypatch):
    query = "민감한 원문 쿼리 12345"
    client, _sidecar = _client(tmp_path, monkeypatch, with_policy=True, llm=FakeLLM(["/Users/me/secret.txt"]))
    response = _free_request(client, query)

    assert query not in response.text
    assert "/Users/me/secret.txt" not in response.text
    assert "<|im_start|>system" not in response.text
    events = _parse_events(response.text)
    assert all(event["data"].get("raw_text_logged") is not True for event in events)
