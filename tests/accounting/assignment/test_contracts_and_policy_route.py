from __future__ import annotations

import json
from pathlib import Path

import pytest

jsonschema = pytest.importorskip("jsonschema")

from butler_pc_core.accounting.assignment.domain import AssignCommand, AssignmentError
from butler_pc_core.accounting.assignment.runtime import AccountingReviewRuntime
from butler_pc_core.accounting.assignment.security import MemoryKeyStore
from butler_pc_core.company_policy.middleware import _route_operation, DEFAULT_ROUTE_OPERATION


ROOT = Path(__file__).resolve().parents[3]
CONTRACTS = ROOT / "butler_pc_core" / "accounting" / "assignment" / "contracts"


def test_integration_lock_matches_schema_and_git_base():
    lock = json.loads((ROOT / "integration_lock.json").read_text(encoding="utf-8"))
    schema = json.loads((CONTRACTS / "integration_lock.schema.json").read_text(encoding="utf-8"))
    jsonschema.Draft202012Validator(schema, format_checker=jsonschema.FormatChecker()).validate(lock)
    assert lock["base_commit"] == "55d0f315e2b375d58c9c2a0263b606e5a757b59e"
    assert lock["base_tree"] == "9d21d32bca294bc9998253f7d1c2f6f88ad71114"


@pytest.mark.parametrize("forged", ["descriptor_digest", "bank_adapter_id", "learned", "actor_id"])
def test_assign_contract_rejects_caller_evidence(forged: str):
    payload = {
        "schema_version": "2.0",
        "account_id": "PL.SGA.PAYMENT_FEE",
        "scope": "THIS_ONLY",
        "registry_digest": "a" * 64,
        "expected_transaction_version": 1,
        forged: "forged",
    }
    with pytest.raises(AssignmentError, match="INVALID_REQUEST_SCHEMA"):
        AssignCommand.from_dict(payload)


@pytest.mark.parametrize(
    "path",
    [
        "/v1/accounting/unaccounted/txn_1234567890123456/assign",
        "/v1/accounting/learned-rules/rule_1234567890123456/deactivate",
        "/v1/accounting/rule-conflicts/conflict_1234567890123456/resolve",
    ],
)
def test_assignment_mutations_are_covered_by_central_policy_gate(path: str):
    assert _route_operation(path, DEFAULT_ROUTE_OPERATION) == ("5", "accounting_classify")


def test_malformed_dynamic_path_is_not_treated_as_valid_mutation():
    assert _route_operation("/v1/accounting/unaccounted/../../assign", DEFAULT_ROUTE_OPERATION) is None


def test_actual_sidecar_route_graph_contains_complete_accounting_review_api():
    import butler_sidecar

    def paths(routes):
        found = set()
        for route in routes:
            path = getattr(route, "path", None)
            if path is not None:
                found.add(path)
            nested = getattr(route, "routes", None)
            if nested is not None:
                found.update(paths(nested))
            original_router = getattr(route, "original_router", None)
            if original_router is not None:
                found.update(paths(original_router.routes))
        return found

    published = paths(butler_sidecar.app.routes)
    assert {
        "/v1/accounting/batches/{batch_id}/review-summary",
        "/v1/accounting/batches/{batch_id}/unaccounted",
        "/v1/accounting/chart-of-accounts",
        "/v1/accounting/unaccounted/{txn_id}/assign",
        "/v1/accounting/learned-rules",
        "/v1/accounting/learned-rules/{rule_id}/deactivate",
        "/v1/accounting/rule-conflicts/{conflict_id}/resolve",
        "/v1/accounting/review-capability",
    } <= published


def test_bundled_unapproved_registry_and_capability_match_wire_schemas(tmp_path: Path):
    runtime = AccountingReviewRuntime(
        db_path=tmp_path / "schema.sqlite3",
        key_store=MemoryKeyStore(key=b"s" * 32),
    )
    profile = type(
        "Profile",
        (),
        {"status": "ACTIVE", "profile_id": "schema-tenant", "profile_digest": "d" * 64},
    )()
    pairs = (
        ("chart_registry_view.schema.json", runtime.registry.public_view()),
        ("capability_status.schema.json", runtime.capability(runtime.context_from_profile(profile))),
    )
    for schema_name, payload in pairs:
        schema = json.loads((CONTRACTS / schema_name).read_text(encoding="utf-8"))
        jsonschema.Draft202012Validator(schema, format_checker=jsonschema.FormatChecker()).validate(payload)


def test_conflict_problem_extensions_match_wire_schema():
    problem = AssignmentError(
        "LEARNED_RULE_CONFLICT",
        409,
        "A suggestion rule conflicts with the selected account.",
        actions=("RESOLVE_CONFLICT:conflict_1234567890123456",),
        current_version=1,
        conflict_id="conflict_1234567890123456",
        conflict_version=1,
        existing_account_id="POSTING.EXISTING",
        proposed_account_id="POSTING.PROPOSED",
    ).problem("request_12345678")
    schema = json.loads((CONTRACTS / "problem_detail.schema.json").read_text(encoding="utf-8"))
    jsonschema.Draft202012Validator(schema, format_checker=jsonschema.FormatChecker()).validate(problem)
