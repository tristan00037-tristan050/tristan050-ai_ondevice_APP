from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from ac25 import repo_contract_runner, strict_receipt_validator
from ac25.strict_receipt import StrictReceiptError
from ac25.strict_v44 import require_authority_verdict, validate_strict_receipt
from ac25.v44_types import StrictValidationVerdict
from tests.box5_ac25.v44_fixtures import valid_input


ROOT = Path(__file__).resolve().parents[2]
CANDIDATE_WORKFLOW = ROOT / ".github/workflows/box5-ac25-stage-a-smoke.yml"


def test_candidate_workflow_cannot_issue_final_receipt():
    source = CANDIDATE_WORKFLOW.read_text(encoding="utf-8")
    assert "FINAL_RECEIPT_SHA256=" not in source
    assert "AC25_PASS=1" not in source
    assert "strict_receipt_validator gate" not in source


def test_candidate_workflow_cannot_supply_authority_policy():
    source = CANDIDATE_WORKFLOW.read_text(encoding="utf-8")
    assert "AUTHORITY_POLICY_SOURCE=" not in source
    assert "AUTHORITY_POLICY_SHA256=" not in source
    assert "authority-policy" not in source.lower()


def test_authority_workflow_is_preprovisioned_outside_pr904():
    inp = valid_input()
    assert inp.authority_source.protected is True
    assert inp.authority_source.candidate_controlled is False
    assert inp.authority_source.source.repository_id != inp.candidate_bundle.repository_id


def test_authority_workflow_never_executes_candidate_code():
    inp = valid_input()
    authority = inp.remote[-1]
    assert authority.repository_id != inp.candidate_bundle.repository_id
    assert authority.workflow_sha != inp.candidate_bundle.candidate_head


def test_validator_failure_fails_authority_job():
    with pytest.raises(StrictReceiptError, match="AUTHORITY_POLICY_NOT_PROVISIONED"):
        require_authority_verdict(
            StrictValidationVerdict(False, ("AUTHORITY_POLICY_NOT_PROVISIONED",), ("policy",))
        )


def test_receipt_step_requires_validator_success():
    require_authority_verdict(StrictValidationVerdict(True, (), ()))
    with pytest.raises(StrictReceiptError, match="STRICT_VERDICT_CONTRACT_INVALID"):
        require_authority_verdict(StrictValidationVerdict(True, ("failure",), ()))


def test_authority_workflow_source_is_protected_default_branch():
    inp = valid_input()
    authority = inp.remote[-1]
    assert authority.event == "workflow_dispatch"
    assert inp.authority_source.protected
    assert authority.workflow_sha == inp.authority_source.source.commit_sha


def test_full_valid_control_state_passes():
    verdict = strict_receipt_validator.validate_strict_receipt(valid_input())
    assert strict_receipt_validator.validate_strict_receipt is validate_strict_receipt
    assert verdict == StrictValidationVerdict(True, (), ())


def test_missing_external_authority_execution_is_blocked():
    inp = valid_input()
    verdict = validate_strict_receipt(replace(inp, remote=inp.remote[:-1]))
    assert verdict.ok is False
    assert "AUTHORITY_WORKFLOW_NOT_PROVISIONED" in verdict.failures


def test_authority_execution_must_be_workflow_dispatch():
    inp = valid_input()
    remote = inp.remote[:-1] + (replace(inp.remote[-1], event="pull_request"),)
    verdict = validate_strict_receipt(replace(inp, remote=remote))
    assert verdict.ok is False
    assert "AUTHORITY_WORKFLOW_NOT_PROVISIONED" in verdict.failures


def test_candidate_execution_must_be_pull_request():
    inp = valid_input()
    remote = (replace(inp.remote[0], event="workflow_dispatch"),) + inp.remote[1:]
    verdict = validate_strict_receipt(replace(inp, remote=remote))
    assert verdict.ok is False
    assert "REMOTE_SCHEMA_UNSUPPORTED" in verdict.failures


def test_v44_contract_entrypoint_is_measured_but_not_base_equality_blocked():
    path = "scripts/verify/verify_repo_contracts.sh"
    assert path in repo_contract_runner.PROTECTED_GUARD_PATHS
    assert path not in repo_contract_runner.MUTATION_FORBIDDEN_GUARD_PATHS
    assert set(repo_contract_runner.MUTATION_FORBIDDEN_GUARD_PATHS) == set(
        repo_contract_runner.PROTECTED_GUARD_PATHS
    ) - {path}
