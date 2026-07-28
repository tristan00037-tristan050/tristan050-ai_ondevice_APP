from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from butler_pc_core.cards.box3.adapters import company_format_adapter
from butler_pc_core.company_fact import resolver as resolver_module
from butler_pc_core.company_fact.resolver import CompanyKnowledgeResolver
from butler_pc_core.company_fact.storage import CompanyFactStore
from butler_pc_core.company_learning.folder_ingest import ingest_folder
from butler_pc_core.company_learning.handoff import (
    create_company_learning_candidate,
)
from butler_pc_core.company_learning.job_store import CompanyLearningJobStore
from butler_pc_core.company_policy import middleware as policy_middleware
from butler_pc_core.company_policy.contracts import (
    AccessRule,
    AdminContext,
    make_company_policy,
    sha256_text,
)
from butler_pc_core.company_policy.middleware import add_policy_gate_middleware
from butler_pc_core.company_policy.storage import CompanyFormatStore, PolicyStore
from butler_pc_core.connect_loop.learning_event_store import LearningEventStore
from butler_pc_core.learning_capability.authorities import (
    CompanyFactAuthority,
    CompanyFormatAuthority,
    CompanyPolicyAuthority,
    FolderLearningAuthority,
)
from butler_pc_core.learning_capability.consumer_bindings import (
    ConsumerBindingStore,
)
from butler_pc_core.learning_capability.contracts import (
    CapabilityState,
    derive_state,
)


def _admin() -> AdminContext:
    return AdminContext(
        admin_id_digest=sha256_text("test-admin"),
        role="admin",
        admin_session_digest=sha256_text("test-session"),
        auth_method="test_only",
    )


def _install_policy(store: PolicyStore, monkeypatch):
    import butler_pc_core.company_policy.storage as storage_module

    monkeypatch.setattr(
        storage_module,
        "verify_admin_context",
        lambda admin, operation: admin,
    )
    policy = make_company_policy(
        registered_by_digest=_admin().admin_id_digest,
        access_rules=[
            AccessRule(
                dept_digest=sha256_text("dept-unknown"),
                role="employee",
                doc_grade="restricted",
                decision="allow",
                reason_code="TEST_ALLOW",
            )
        ],
    )
    store.save_policy(policy, _admin())
    return policy


def _install_fact(store: CompanyFactStore, monkeypatch):
    import butler_pc_core.company_fact.storage as storage_module

    monkeypatch.setattr(
        storage_module,
        "verify_admin_context",
        lambda admin, operation: admin,
    )
    candidate, _ = store.save_candidate(
        category="company_only",
        question_patterns=[
            "zephyr widget approval code",
            "what is the zephyr widget approval code",
        ],
        keywords_required=["zephyr", "widget"],
        keywords_any=["approval", "code"],
        answer_runtime_text="The company-only approval code is ZEPHYR-42.",
        source="company_policy_manual",
        confidence=0.9,
    )
    active, _ = store.approve_candidate(candidate.fact_id, _admin())
    return active


def _install_format(store: CompanyFormatStore, monkeypatch):
    import butler_pc_core.company_policy.storage as storage_module

    monkeypatch.setattr(
        storage_module,
        "verify_admin_context",
        lambda admin, operation: admin,
    )
    fmt, _ = store.register_format(
        template_runtime_text="Company report\n{draft}",
        format_kind="report",
        title_runtime_text="Company report",
        language="en",
        dept_digest=sha256_text("dept-unknown"),
        admin=_admin(),
    )
    return fmt


def test_company_policy_in_use_requires_active_policy_and_real_policy_gate_consumer(
    tmp_path,
    monkeypatch,
):
    policy_store = PolicyStore(root=tmp_path / "policy")
    policy = _install_policy(policy_store, monkeypatch)
    bindings = ConsumerBindingStore(tmp_path / "bindings.json")
    authority = CompanyPolicyAuthority(policy_store, bindings)
    assert derive_state(authority.probe()) is CapabilityState.REGISTERED_ONLY

    monkeypatch.setattr(
        policy_middleware,
        "default_consumer_binding_store",
        lambda: bindings,
    )
    app = FastAPI()
    add_policy_gate_middleware(app, policy_store=policy_store)

    @app.post("/v1/cards/2/rewrite")
    async def protected_product_route():
        return {"ok": True}

    response = TestClient(app).post(
        "/v1/cards/2/rewrite",
        headers={"x-request-id": "request-12345678"},
    )
    assert response.status_code == 200
    assert response.headers["x-applied-policy-digest"] == policy.policy_digest
    assert derive_state(authority.probe()) is CapabilityState.IN_USE


def test_company_fact_in_use_requires_active_fact_resolved_by_real_product_consumer(
    tmp_path,
    monkeypatch,
):
    store = CompanyFactStore(root=tmp_path / "facts")
    active = _install_fact(store, monkeypatch)
    bindings = ConsumerBindingStore(tmp_path / "bindings.json")
    authority = CompanyFactAuthority(store, bindings)
    assert derive_state(authority.probe()) is CapabilityState.REGISTERED_ONLY

    monkeypatch.setattr(
        resolver_module,
        "default_consumer_binding_store",
        lambda: bindings,
    )
    result = CompanyKnowledgeResolver(company_store=store).resolve(
        "what is the zephyr widget approval code"
    )
    assert result.source == "company"
    assert result.fact_id == active.fact_id
    assert result.fact_digest == active.fact_digest
    assert derive_state(authority.probe()) is CapabilityState.IN_USE


def test_company_format_registered_only_and_in_use_are_not_self_claimed(
    tmp_path,
    monkeypatch,
):
    store = CompanyFormatStore(root=tmp_path / "formats")
    company_format = _install_format(store, monkeypatch)
    bindings = ConsumerBindingStore(tmp_path / "bindings.json")
    authority = CompanyFormatAuthority(store, bindings)
    assert derive_state(authority.probe()) is CapabilityState.REGISTERED_ONLY

    monkeypatch.setattr(
        company_format_adapter,
        "default_consumer_binding_store",
        lambda: bindings,
    )
    applied = company_format_adapter.apply_company_format_runtime(
        draft_text_runtime_only="Quarterly summary",
        format_id=company_format.format_id,
        store=store,
    )
    assert applied.format_applied is True
    assert applied.format_digest == company_format.format_digest
    assert derive_state(authority.probe()) is CapabilityState.IN_USE


def test_folder_learning_ignores_ephemeral_job_and_uses_persisted_handoff_authority(
    tmp_path,
):
    folder = tmp_path / "docs"
    folder.mkdir()
    (folder / "policy.txt").write_text(
        "Company policy approval workflow and local review process.",
        encoding="utf-8",
    )
    job = CompanyLearningJobStore().create_completed(ingest_folder(str(folder)))
    bindings = ConsumerBindingStore(tmp_path / "bindings.json")
    event_path = tmp_path / "learning-events.jsonl"
    store = LearningEventStore(jsonl_path=event_path)
    authority = FolderLearningAuthority(store, bindings)
    assert derive_state(authority.probe()) is CapabilityState.UNKNOWN

    handoff = create_company_learning_candidate(job, store=store)
    assert handoff.fail_class is None
    assert event_path.exists()
    restarted = LearningEventStore(jsonl_path=event_path)
    restarted_authority = FolderLearningAuthority(restarted, bindings)
    assert (
        derive_state(restarted_authority.probe())
        is CapabilityState.PREVIEW_ONLY
    )

