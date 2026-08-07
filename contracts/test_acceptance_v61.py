from __future__ import annotations

import hashlib
import json
from pathlib import Path

import yaml
from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[1]
SCHEMAS = (
    "helper1-approval-input-provenance-v2.schema.json",
    "helper1-approval-input-inventory-v2.schema.json",
    "helper1-retrieval-benchmark-manifest-v2.schema.json",
    "helper1-retrieval-case-v2.schema.json",
    "helper1-answer-case-v2.schema.json",
    "helper1-retrieval-quality-report-v2.schema.json",
    "helper1-device-measurement-v2.schema.json",
    "helper1-evaluation-run-subject-v2.schema.json",
    "helper1-quality-input-provenance-v1.schema.json",
    "helper1-quality-evidence-manifest-v1.schema.json",
)
SCRIPTS = (
    "scripts/ci/helper1_assert_start_tree.py",
    "scripts/ci/helper1_approval_input_fetch.py",
    "scripts/ci/helper1_approval_input_verify.py",
    "scripts/ci/helper1_approval_input_materialize.py",
    "scripts/ci/helper1_approval_input_package.py",
    "scripts/ci/helper1_run_sealed_benchmark.py",
    "scripts/ci/helper1_recompute_quality_report.py",
    "scripts/ci/helper1_measure_device.py",
    "scripts/ci/helper1_build_evaluation_subject.py",
    "scripts/ci/helper1_quality_input_fetch.py",
    "scripts/ci/helper1_quality_evidence_manifest.py",
)


def test_v61_schemas_are_draft_2020_12_valid() -> None:
    for name in SCHEMAS:
        schema = json.loads((ROOT / "contracts" / name).read_text(encoding="utf-8"))
        Draft202012Validator.check_schema(schema)


def test_v61_required_runtime_and_verifier_nodes_exist() -> None:
    for path in SCRIPTS:
        assert (ROOT / path).is_file(), path
    for path in (
        "butler_pc_core/helper1/approval_input.py",
        "butler_pc_core/helper1/failure_codes.py",
        ".github/workflows/helper1-v2-approval-evidence.yml",
    ):
        assert (ROOT / path).is_file(), path


def test_approval_workflow_has_least_privilege_and_exact_artifact_inputs() -> None:
    path = ROOT / ".github/workflows/helper1-v2-approval-evidence.yml"
    workflow = yaml.load(path.read_text(encoding="utf-8"), Loader=yaml.BaseLoader)
    assert workflow["permissions"] == {"contents": "read", "actions": "read"}
    job = workflow["jobs"]["approval-evidence"]
    assert job["environment"] == "helper1-v2-protected-approval"
    steps = job["steps"]
    assert all("pull_request_target" not in json.dumps(step) for step in steps)
    run_steps = "\n".join(step.get("run", "") for step in steps)
    for flag in (
        "--run-id",
        "--run-attempt",
        "--artifact-id",
        "--artifact-name",
        "--producer-workflow-ref",
        "--producer-workflow-sha256",
    ):
        assert flag in run_steps
    assert "helper1_approval_input_materialize.py" in run_steps
    assert "--workflow-sha256" in run_steps
    assert "--canonical-subject-sha256" in run_steps


def test_approval_workflow_bytes_are_pinned_by_protected_package_verifier() -> None:
    from scripts.ci.helper1_producer_package import (
        APPROVAL_PRODUCER_WORKFLOW_SHA256,
    )

    workflow = ROOT / ".github/workflows/helper1-v2-approval-evidence.yml"
    assert hashlib.sha256(workflow.read_bytes()).hexdigest() == APPROVAL_PRODUCER_WORKFLOW_SHA256


def test_untrusted_producer_cannot_emit_v2_package_without_approval_input() -> None:
    workflow = yaml.load(
        (ROOT / ".github/workflows/helper1-v2-evidence.yml").read_text(encoding="utf-8"),
        Loader=yaml.BaseLoader,
    )
    steps = workflow["jobs"]["untrusted-producer"]["steps"]
    require_step = next(step for step in steps if step.get("name") == "Require explicit protected approval producer")
    assert require_step["if"] == "github.event_name != 'workflow_dispatch'"
    assert "NO_EXPLICIT_PRODUCER" in require_step["run"]
    build_step = next(step for step in steps if step.get("name") == "Build fixed-path Helper1 candidate package")
    assert build_step["if"] == "github.event_name == 'workflow_dispatch'"
    assert "--approval-input-artifact" in build_step["run"]
    assert "--approval-input-provenance" in build_step["run"]
    materialize_step = next(
        step for step in steps if step.get("name") == "Fetch exact protected approval input"
    )
    assert "--workflow-sha256" in materialize_step["run"]
    assert "--canonical-subject-sha256" in materialize_step["run"]


def test_protected_quality_chain_is_executable_and_bound_to_candidate_package() -> None:
    workflow_path = ROOT / ".github/workflows/helper1-v2-evidence.yml"
    workflow = yaml.load(workflow_path.read_text(encoding="utf-8"), Loader=yaml.BaseLoader)
    job = workflow["jobs"]["untrusted-producer"]
    assert job["runs-on"] == ["self-hosted", "macOS", "ARM64", "helper1-quality"]
    steps = job["steps"]
    names = [step.get("name") for step in steps]
    ordered = (
        "Fetch exact protected approval input",
        "Assemble complete product approval inventory",
        "Fetch exact protected SearchQuality input",
        "Execute protected SearchQuality chain",
        "Build fixed-path Helper1 candidate package",
    )
    assert [names.index(name) for name in ordered] == sorted(names.index(name) for name in ordered)
    quality = next(step for step in steps if step.get("name") == ordered[3])["run"]
    for command in (
        "helper1_assert_start_tree.py",
        "helper1_build_evaluation_subject.py",
        "helper1_run_sealed_benchmark.py",
        "helper1_recompute_quality_report.py",
        "helper1_measure_device.py",
        "helper1_quality_evidence_manifest.py",
    ):
        assert quality.count(command) >= 1
    assert "for device in M3 M4" in quality
    assert "--evaluation-run-id" in quality
    assert "--producer-run-id" in quality
    build = next(step for step in steps if step.get("name") == ordered[4])["run"]
    assert '--quality-evidence-root "${RUNNER_TEMP}/helper1-build/search-quality"' in build
