from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from butler_pc_core.cards.box3.adapters import company_format_adapter
from butler_pc_core.company_fact import resolver as resolver_module
from butler_pc_core.company_fact.resolver import CompanyKnowledgeResolver
from butler_pc_core.company_fact.storage import CompanyFactStore
from butler_pc_core.company_learning.folder_ingest import ingest_folder
from butler_pc_core.company_learning.handoff import create_company_learning_candidate
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
from butler_pc_core.learning_capability.consumer_bindings import ConsumerBindingStore
from butler_pc_core.learning_capability.generation_store import DurableGenerationStore
from butler_pc_core.learning_capability.service import LearningCapabilityService


def test_all_four_states_are_derived_from_real_stores_and_consumers(
    tmp_path,
    monkeypatch,
):
    import butler_pc_core.company_fact.storage as fact_storage_module
    import butler_pc_core.company_policy.storage as policy_storage_module

    monkeypatch.setattr(
        policy_storage_module,
        "verify_admin_context",
        lambda admin, operation: admin,
    )
    monkeypatch.setattr(
        fact_storage_module,
        "verify_admin_context",
        lambda admin, operation: admin,
    )
    admin = AdminContext(
        admin_id_digest=sha256_text("integration-admin"),
        role="admin",
        admin_session_digest=sha256_text("integration-session"),
        auth_method="test_only",
    )
    policy_store = PolicyStore(root=tmp_path / "policy")
    policy = make_company_policy(
        registered_by_digest=admin.admin_id_digest,
        access_rules=[
            AccessRule(
                dept_digest=sha256_text("dept-unknown"),
                role="employee",
                doc_grade="restricted",
                decision="allow",
                reason_code="INTEGRATION_ALLOW",
            )
        ],
    )
    policy_store.save_policy(policy, admin)

    fact_store = CompanyFactStore(root=tmp_path / "facts")
    candidate, _ = fact_store.save_candidate(
        category="integration",
        question_patterns=[
            "orion ledger approval phrase",
            "what is the orion ledger approval phrase",
        ],
        keywords_required=["orion", "ledger"],
        keywords_any=["approval", "phrase"],
        answer_runtime_text="The company approval phrase is ORION-LEDGER.",
        source="integration_company_manual",
        confidence=0.9,
    )
    active_fact, _ = fact_store.approve_candidate(candidate.fact_id, admin)

    format_store = CompanyFormatStore(root=tmp_path / "formats")
    company_format, _ = format_store.register_format(
        template_runtime_text="Approved company format\n{draft}",
        format_kind="report",
        title_runtime_text="Approved company report",
        language="en",
        dept_digest=sha256_text("dept-unknown"),
        admin=admin,
    )

    folder = tmp_path / "docs"
    folder.mkdir()
    (folder / "workflow.txt").write_text(
        "Company workflow, policy, approval, and review instructions.",
        encoding="utf-8",
    )
    job = CompanyLearningJobStore().create_completed(ingest_folder(str(folder)))
    event_store = LearningEventStore(
        jsonl_path=tmp_path / "learning-events.jsonl"
    )
    assert create_company_learning_candidate(job, store=event_store).event

    bindings = ConsumerBindingStore(tmp_path / "bindings.json")
    monkeypatch.setattr(
        policy_middleware,
        "default_consumer_binding_store",
        lambda: bindings,
    )
    monkeypatch.setattr(
        resolver_module,
        "default_consumer_binding_store",
        lambda: bindings,
    )
    monkeypatch.setattr(
        company_format_adapter,
        "default_consumer_binding_store",
        lambda: bindings,
    )

    app = FastAPI()
    add_policy_gate_middleware(app, policy_store=policy_store)

    @app.post("/v1/cards/2/rewrite")
    async def protected_product_route():
        return {"ok": True}

    policy_response = TestClient(app).post(
        "/v1/cards/2/rewrite",
        headers={"x-request-id": "integration-request-123"},
    )
    assert policy_response.status_code == 200
    fact_result = CompanyKnowledgeResolver(company_store=fact_store).resolve(
        "what is the orion ledger approval phrase"
    )
    assert fact_result.source == "company"
    assert fact_result.fact_digest == active_fact.fact_digest
    format_result = company_format_adapter.apply_company_format_runtime(
        draft_text_runtime_only="Quarterly results",
        format_id=company_format.format_id,
        store=format_store,
    )
    assert format_result.format_applied is True

    service = LearningCapabilityService(
        authorities=(
            CompanyPolicyAuthority(policy_store, bindings),
            CompanyFactAuthority(fact_store, bindings),
            CompanyFormatAuthority(format_store, bindings),
            FolderLearningAuthority(event_store, bindings),
        ),
        generation_store=DurableGenerationStore(
            tmp_path / "generation.json"
        ),
    )
    payload = service.snapshot().to_dict()
    assert payload["source"] == "CANONICAL"
    assert payload["capabilities"] == {
        "company_rules": "IN_USE",
        "company_facts": "IN_USE",
        "company_formats": "IN_USE",
        "folder_learning": "PREVIEW_ONLY",
    }

