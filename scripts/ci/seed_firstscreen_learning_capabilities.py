#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))


def _approved_app_data() -> Path:
    configured = os.environ.get("BUTLER_APP_DATA_DIR", "").strip()
    if not configured:
        raise RuntimeError("E2E_APP_DATA_MISSING")
    root = Path(configured).expanduser()
    if not root.is_absolute():
        raise RuntimeError("E2E_APP_DATA_NOT_ABSOLUTE")
    if root.name != "app-data" or root.parent.name != ".playwright-runtime":
        raise RuntimeError("E2E_APP_DATA_SCOPE_REJECTED")
    root.mkdir(parents=True, exist_ok=True)
    return root


def _admin_context():
    from butler_pc_core.company_policy.contracts import AdminContext, sha256_text

    return AdminContext(
        admin_id_digest=sha256_text("firstscreen-e2e-admin"),
        role="admin",
        admin_session_digest=sha256_text("firstscreen-e2e-session"),
        auth_method="tauri_secure_invoke",
    )


def _seed() -> None:
    app_data = _approved_app_data()
    os.chdir(app_data)

    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from butler_pc_core.cards.box3.adapters.company_format_adapter import (
        apply_company_format_runtime,
    )
    from butler_pc_core.company_fact.resolver import CompanyKnowledgeResolver
    from butler_pc_core.company_fact.storage import CompanyFactStore
    from butler_pc_core.company_learning.folder_ingest import ingest_folder
    from butler_pc_core.company_learning.handoff import (
        create_company_learning_candidate,
    )
    from butler_pc_core.company_learning.job_store import CompanyLearningJobStore
    from butler_pc_core.company_policy import admin_auth
    from butler_pc_core.company_policy.contracts import (
        AccessRule,
        make_company_policy,
        sha256_text,
    )
    from butler_pc_core.company_policy.middleware import add_policy_gate_middleware
    from butler_pc_core.company_policy.role_registry import RoleRegistryStore
    from butler_pc_core.company_policy.storage import CompanyFormatStore, PolicyStore
    from butler_pc_core.connect_loop.learning_event_store import LearningEventStore
    from butler_pc_core.learning_capability.authorities import (
        CompanyFactAuthority,
        CompanyFormatAuthority,
        CompanyPolicyAuthority,
        FolderLearningAuthority,
    )
    from butler_pc_core.learning_capability.consumer_bindings import (
        default_consumer_binding_store,
    )
    from butler_pc_core.learning_capability.generation_store import (
        DurableGenerationStore,
    )
    from butler_pc_core.learning_capability.service import LearningCapabilityService

    admin = _admin_context()
    registry = RoleRegistryStore(root=app_data / "e2e-admin-registry")
    if registry.is_empty():
        registry.bootstrap_self_admin(admin)
    admin_auth.get_default_role_registry_store = lambda: registry

    policy_store = PolicyStore()
    policy = make_company_policy(
        registered_by_digest=admin.admin_id_digest,
        access_rules=[
            AccessRule(
                dept_digest=sha256_text("dept-unknown"),
                role="employee",
                doc_grade="restricted",
                decision="allow",
                reason_code="E2E_ALLOW",
            )
        ],
    )
    policy_store.save_policy(policy, admin)

    fact_store = CompanyFactStore()
    candidate, _ = fact_store.save_candidate(
        category="firstscreen_e2e",
        question_patterns=[
            "e2e helios approval phrase",
            "what is the e2e helios approval phrase",
        ],
        keywords_required=["e2e", "helios"],
        keywords_any=["approval", "phrase"],
        answer_runtime_text="The company-only phrase is E2E-HELIOS.",
        source="firstscreen_e2e_manual",
        confidence=0.9,
    )
    fact_store.approve_candidate(candidate.fact_id, admin)

    format_store = CompanyFormatStore()
    company_format, _ = format_store.register_format(
        template_runtime_text="E2E company report\n{draft}",
        format_kind="report",
        title_runtime_text="E2E company report",
        language="en",
        dept_digest=sha256_text("dept-unknown"),
        admin=admin,
    )

    event_store = LearningEventStore(
        jsonl_path=app_data / "company-learning" / "learning_events.jsonl"
    )
    if event_store.capability_summary().candidate_count == 0:
        source = app_data / "e2e-learning-source"
        source.mkdir(parents=True, exist_ok=True)
        (source / "workflow.txt").write_text(
            "Company workflow, approval, policy, and review instructions.",
            encoding="utf-8",
        )
        job = CompanyLearningJobStore().create_completed(
            ingest_folder(str(source))
        )
        result = create_company_learning_candidate(job, store=event_store)
        if result.event is None:
            raise RuntimeError("E2E_FOLDER_HANDOFF_FAILED")

    app = FastAPI()
    add_policy_gate_middleware(app, policy_store=policy_store)

    @app.post("/v1/cards/2/rewrite")
    async def _protected_product_consumer():
        return {"ok": True}

    response = TestClient(app).post(
        "/v1/cards/2/rewrite",
        headers={"x-request-id": "firstscreen-e2e-request"},
    )
    if response.status_code != 200:
        raise RuntimeError("E2E_POLICY_CONSUMER_FAILED")

    fact_result = CompanyKnowledgeResolver(company_store=fact_store).resolve(
        "what is the e2e helios approval phrase"
    )
    active_fact_digests = {
        record.fact_digest for record in fact_store.load_active_facts()
    }
    if (
        fact_result.source != "company"
        or fact_result.fact_digest not in active_fact_digests
    ):
        raise RuntimeError("E2E_FACT_CONSUMER_FAILED")

    format_result = apply_company_format_runtime(
        draft_text_runtime_only="Quarterly E2E results",
        format_id=company_format.format_id,
        store=format_store,
    )
    if not format_result.format_applied:
        raise RuntimeError("E2E_FORMAT_CONSUMER_FAILED")

    bindings = default_consumer_binding_store()
    service = LearningCapabilityService(
        authorities=(
            CompanyPolicyAuthority(policy_store, bindings),
            CompanyFactAuthority(fact_store, bindings),
            CompanyFormatAuthority(format_store, bindings),
            FolderLearningAuthority(event_store, bindings),
        ),
        generation_store=DurableGenerationStore(
            app_data / "learning-capability" / "generation.json"
        ),
    )
    payload = service.snapshot().to_dict()
    if payload["capabilities"] != {
        "company_policy": "IN_USE",
        "company_fact": "IN_USE",
        "company_format": "IN_USE",
        "folder_learning": "NOT_REGISTERED",
    }:
        raise RuntimeError("E2E_CANONICAL_SEED_MISMATCH")
    print("FIRSTSCREEN_LEARNING_SEED_OK=1")


def _serve(*, host: str, port: int) -> None:
    import uvicorn

    uvicorn.run(
        "butler_sidecar:app",
        host=host,
        port=port,
        reload=False,
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "mode",
        choices=("seed", "seed-and-serve", "seed-stale-and-serve"),
    )
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    if args.mode == "seed":
        _seed()
        return 0
    if args.mode == "seed-and-serve":
        # Keep the product consumer bindings and the sidecar in one process.
        # Consumer binding v2 intentionally binds IN_USE to the in-memory
        # runtime instance; a seed process followed by a second Python process
        # would correctly invalidate those bindings as stale.
        _seed()
        _serve(host=args.host, port=args.port)
        return 0

    # Build the fixture only through the real product authorities/consumers,
    # then start the sidecar in a distinct runtime. The persisted consumer
    # binding is therefore stale by design and the canonical endpoint must
    # fail closed with 503. No route interception or direct state mutation is
    # used by this real-sidecar attack path.
    subprocess.run(
        [sys.executable, str(Path(__file__).resolve()), "seed"],
        check=True,
        env=os.environ.copy(),
    )
    _serve(host=args.host, port=args.port)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
