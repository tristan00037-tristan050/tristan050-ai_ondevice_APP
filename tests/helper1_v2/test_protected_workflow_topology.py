from __future__ import annotations

import ast
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
PRODUCER = ROOT / ".github/workflows/helper1-v2-evidence.yml"
TRUSTED = ROOT / ".github/workflows/helper1-v2-trusted-verifier.yml"
POLICY = ROOT / "contracts/helper1/trusted-verifier-policy-v1.json"
VERIFIER = ROOT / "scripts/ci/helper1_trusted_verifier.py"
SUBJECT_BINDING = ROOT / "scripts/ci/helper1_subject_binding.py"
SEMANTICS = ROOT / "scripts/ci/helper1_evidence_semantics.py"
PUBLISHER = ROOT / "scripts/ci/publish_helper1_subject_check.py"
POSTGRES_PROBE = ROOT / "scripts/ci/helper1_postgresql_replay_probe.py"
APPROVAL_CLOSURE = ROOT / "butler_pc_core/helper1/approval_closure.py"
CANONICAL_JSON = ROOT / "butler_pc_core/helper1/canonical_json.py"
EXECUTION = ROOT / "butler_pc_core/helper1/execution.py"
REPLAY_STORE = ROOT / "butler_pc_core/helper1/replay_store.py"
RETRIEVAL_POLICY = ROOT / "butler_pc_core/helper1/retrieval_policy.py"
CODEOWNERS = ROOT / ".github/CODEOWNERS"


def test_trusted_verifier_runs_from_protected_default_branch_only():
    producer = PRODUCER.read_text(encoding="utf-8")
    trusted = TRUSTED.read_text(encoding="utf-8")

    assert "workflow_run:" in trusted
    assert "workflows: [helper1-v2-evidence-producer]" in trusted
    assert "ref: ${{ github.sha }}" in trusted
    assert "persist-credentials: false" in trusted
    assert "checks: write" in trusted
    assert "environment: helper1-production-verifier" in trusted
    assert "HELPER1_APPROVAL_REPLAY_DSN: ${{ secrets.HELPER1_APPROVAL_REPLAY_DSN }}" in trusted
    assert "python scripts/ci/helper1_postgresql_replay_probe.py" in trusted
    assert "HELPER1_REPLAY_PROBE_RUN_ID: ${{ github.run_id }}-${{ github.run_attempt }}" in trusted
    assert "HELPER1_REPLAY_PROBE_OUTCOME: ${{ steps.replay-store-probe.outcome }}" in trusted
    assert "REPLAY_PROBE_OUTCOME: ${{ steps.replay-store-probe.outcome }}" in trusted
    assert "HELPER1_APPROVAL_REPLAY_DB" not in trusted
    assert "python scripts/ci/helper1_subject_binding.py" in trusted
    assert '--fetch-event "${GITHUB_EVENT_PATH}"' in trusted
    assert '--subject "${RUNNER_TEMP}/helper1/input/CANONICAL_SUBJECT.json"' in trusted
    assert "checkout" not in trusted.split(
        "Recompute canonical subject and fetch exact Git object without checkout", 1
    )[1]
    assert "ref: ${{ github.event.workflow_run.head_sha }}" not in trusted
    assert "persist-credentials: false" in producer


def test_submission_is_downloaded_from_same_repository_but_never_executed():
    trusted = TRUSTED.read_text(encoding="utf-8")
    verifier = VERIFIER.read_text(encoding="utf-8")

    assert '--repo "${GITHUB_REPOSITORY}"' in trusted
    assert '--name "helper1-v2-evidence-${PRODUCER_RUN_ID}-${PRODUCER_RUN_ATTEMPT}"' in trusted
    assert "${RUNNER_TEMP}/helper1/input/evidence" in trusted
    assert "${RUNNER_TEMP}/helper1/input/artifacts" in trusted
    assert "python ${RUNNER_TEMP}" not in trusted
    assert "repository.get(\"full_name\") != policy[\"repository\"]" in verifier
    assert "value.get(\"subject_commit\") != expected_commit" in verifier
    assert "verify_artifact_object(artifact_root, digest)" in verifier
    assert "expected_tree=subject_tree" in verifier
    assert "resolve_commit_tree(ROOT, subject_commit)" in verifier


def test_protected_verifier_fingerprint_is_exactly_pinned():
    import hashlib

    policy = json.loads(POLICY.read_text(encoding="utf-8"))
    observed = "sha256:" + hashlib.sha256(VERIFIER.read_bytes()).hexdigest()

    assert policy["protected_verifier_sha256"] == observed
    assert policy["protected_components_sha256"] == {
        "scripts/ci/helper1_trusted_verifier.py": observed,
        "scripts/ci/helper1_subject_binding.py": "sha256:" + hashlib.sha256(SUBJECT_BINDING.read_bytes()).hexdigest(),
        "scripts/ci/helper1_evidence_semantics.py": "sha256:" + hashlib.sha256(SEMANTICS.read_bytes()).hexdigest(),
        "scripts/ci/publish_helper1_subject_check.py": "sha256:" + hashlib.sha256(PUBLISHER.read_bytes()).hexdigest(),
        "scripts/ci/helper1_postgresql_replay_probe.py": "sha256:" + hashlib.sha256(POSTGRES_PROBE.read_bytes()).hexdigest(),
        "butler_pc_core/helper1/approval_closure.py": "sha256:" + hashlib.sha256(APPROVAL_CLOSURE.read_bytes()).hexdigest(),
        "butler_pc_core/helper1/canonical_json.py": "sha256:" + hashlib.sha256(CANONICAL_JSON.read_bytes()).hexdigest(),
        "butler_pc_core/helper1/execution.py": "sha256:" + hashlib.sha256(EXECUTION.read_bytes()).hexdigest(),
        "butler_pc_core/helper1/replay_store.py": "sha256:" + hashlib.sha256(REPLAY_STORE.read_bytes()).hexdigest(),
        "butler_pc_core/helper1/retrieval_policy.py": "sha256:" + hashlib.sha256(RETRIEVAL_POLICY.read_bytes()).hexdigest(),
    }
    assert policy["policy_epoch"] == 2
    assert policy["enabled"] is False
    assert policy["approved_public_key_b64"] is None
    assert policy["approved_verdict_public_key_b64"] is None
    assert policy["approval_policy_sha256"] is None
    assert policy["approved_activation_public_key_b64"] is None


def test_protected_success_path_invokes_a4_closure_before_verdict() -> None:
    source = VERIFIER.read_text(encoding="utf-8")
    tree = ast.parse(source)
    main = next(
        node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "main"
    )
    calls = [
        node
        for node in ast.walk(main)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "verify_approval_closure"
    ]
    assert len(calls) == 1
    verdict_lines = [
        node.lineno
        for node in ast.walk(main)
        if isinstance(node, ast.Constant) and node.value == "CODE_PASS=1"
    ]
    assert len(verdict_lines) == 1
    assert calls[0].lineno < verdict_lines[0]


def test_existing_helper1_codeowners_rules_are_preserved_and_a4_is_owned() -> None:
    owners = CODEOWNERS.read_text(encoding="utf-8")
    preserved = (
        "/contracts/helper1/trusted-verifier-policy-v1.json",
        "/scripts/ci/helper1_trusted_verifier.py",
        "/scripts/verify_helper1_v2.py",
        "/.github/workflows/helper1-v2-evidence.yml",
        "/.github/workflows/helper1-v2-trusted-verifier.yml",
        "/tests/helper1_v2/test_self_selected_trust_regression.py",
        "/scripts/ci/helper1_subject_binding.py",
        "/scripts/ci/helper1_evidence_semantics.py",
        "/scripts/ci/publish_helper1_subject_check.py",
        "/scripts/ci/helper1_postgresql_replay_probe.py",
        "/tests/helper1_v2/test_protected_workflow_topology.py",
    )
    added = (
        "/butler_pc_core/helper1/approval_closure.py",
        "/butler_pc_core/helper1/canonical_json.py",
        "/butler_pc_core/helper1/execution.py",
        "/butler_pc_core/helper1/retrieval_policy.py",
        "/butler_pc_core/helper1/replay_store.py",
        "/contracts/helper1/retrieval-approval-trust-policy-v1.json",
        "/tests/helper1_v2/vectors/**",
    )
    assert all(owners.count(path) == 1 for path in (*preserved, *added))


def test_postgresql_probe_fails_closed_without_protected_dsn() -> None:
    environment = dict(os.environ)
    environment.pop("HELPER1_APPROVAL_REPLAY_DSN", None)
    environment["HELPER1_REPLAY_PROBE_RUN_ID"] = "fixture-1"
    completed = subprocess.run(
        [sys.executable, str(POSTGRES_PROBE)],
        cwd=ROOT,
        env=environment,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=30,
        check=False,
    )
    assert completed.returncode == 1
    assert completed.stdout.splitlines() == [
        "HELPER1_POSTGRES_REPLAY_PROBE_OK=0",
        "ERROR_CODE=APPROVAL_REPLAY_STORE_UNAVAILABLE",
    ]
    assert completed.stderr == ""



def test_subject_check_is_published_after_verdict_preservation() -> None:
    trusted = TRUSTED.read_text(encoding="utf-8")
    preserve = trusted.index("Preserve immutable subject-bound verdict")
    publish = trusted.index("Publish fixed check on exact subject SHA")
    enforce = trusted.index("Enforce protected subject gate")

    assert preserve < publish < enforce
    assert "helper1-v2-protected-verdict-${{ github.event.workflow_run.head_sha }}" in trusted
    assert "--publish" in trusted
    assert "HELPER1_PRESERVE_OUTCOME" in trusted
    assert "PUBLISH_OUTCOME" in trusted
    assert "continue-on-error: true" in trusted


def test_fixed_required_check_identity_is_declared_but_activation_stays_disabled() -> None:
    policy = json.loads(POLICY.read_text(encoding="utf-8"))
    publisher = PUBLISHER.read_text(encoding="utf-8")

    assert policy["subject_check_name"] == "helper1-v2/protected-verdict"
    assert policy["subject_check_app_slug"] == "github-actions"
    assert policy["subject_check_required"] is True
    assert policy["enabled"] is False
    assert "head_sha" in publisher
    assert "resolve_commit_tree(ROOT, subject)" in publisher
    assert "PROTECTED_PREREQUISITE_FAILED" in publisher


def test_subject_fetch_supports_push_merge_queue_and_base_pull_ref_without_checkout() -> None:
    binding = SUBJECT_BINDING.read_text(encoding="utf-8")

    assert "fetch_subject_object" in binding
    assert "--no-tags" in binding
    assert "--depth=1" in binding
    assert "refs/pull/{pull_number}/head" in binding
    assert "FETCH_HEAD^{commit}" in binding
    assert "observed != subject" in binding
    assert "[\"checkout\"" not in binding
