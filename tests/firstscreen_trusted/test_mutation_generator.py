from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

import pytest


pytestmark = pytest.mark.no_sidecar_token

ROOT = Path(__file__).resolve().parents[2]
CONTEXTS = (
    "contexts/firstscreen-v9-unit-context.json",
    "contexts/firstscreen-v9-real-sidecar-context.json",
    "contexts/firstscreen-v9-real-sidecar-unavailable-context.json",
    "contexts/contract-context.json",
    "contexts/authorities-context.json",
    "contexts/product-integration-context.json",
    "contexts/windows-context.json",
    "contexts/node-verifier-context.json",
    "contexts/node-evidence-context.json",
)


def test_three_seed_mutation_gate_rejects_all_3000_cases(
    tmp_path: Path,
) -> None:
    repository = "tristan00037-tristan050/tristan050-ai_ondevice_APP"
    head = "a" * 40
    tree = "b" * 40
    workflow_ref = (
        f"{repository}/.github/workflows/firstscreen-v2-5.yml"
        "@refs/pull/886/merge"
    )
    metadata = {
        "schema_version": 1,
        "repository": repository,
        "event_name": "pull_request",
        "pull_request": 886,
        "subject_head": head,
        "tree_oid": {"algorithm": "sha1", "hex": tree},
        "producer": {
            "run_id": "123",
            "run_attempt": 1,
            "workflow_ref": workflow_ref,
        },
    }
    metadata_path = tmp_path / "metadata.json"
    metadata_path.write_text(json.dumps(metadata) + "\n", encoding="utf-8")
    package = tmp_path / "package"
    for index, relative_name in enumerate(CONTEXTS):
        path = package / relative_name
        path.parent.mkdir(parents=True, exist_ok=True)
        report_digest = hashlib.sha256(
            f"report-{index}".encode()
        ).hexdigest()
        context = {
            "schema_version": 2,
            "repository": repository,
            "event_name": "pull_request",
            "pull_request": 886,
            "suite": f"suite-{index}",
            "subject_pr_head": head,
            "execution_commit": head,
            "tree_oid": {"algorithm": "sha1", "hex": tree},
            "workflow_run_id": "123",
            "workflow_run_attempt": 1,
            "workflow_ref": workflow_ref,
            "job_name": f"job-{index}",
            "runner": "node",
            "platform": "ubuntu",
            "command": "node test",
            "report_path": f"reports/report-{index}.json",
            "tool_versions": {"node": "24"},
            "started_at": "2026-07-29T00:00:00Z",
            "finished_at": "2026-07-29T00:00:01Z",
            "os": "Linux",
            "arch": "X64",
            "report_sha256": report_digest,
        }
        path.write_text(json.dumps(context) + "\n", encoding="utf-8")
    output = tmp_path / "mutations.json"
    completed = subprocess.run(
        [
            "node",
            str(ROOT / "scripts/ci/trusted_firstscreen_mutations.mjs"),
            "--manifest",
            str(ROOT / "butler-desktop/acceptance/required-tests.v3.json"),
            "--metadata",
            str(metadata_path),
            "--package",
            str(package),
            "--historical",
            str(
                ROOT
                / "tests/firstscreen_trusted/fixtures/"
                "historical_attacks.v1.json"
            ),
            "--output",
            str(output),
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
        timeout=30,
    )
    assert completed.returncode == 0, completed.stdout
    result = json.loads(output.read_text(encoding="utf-8"))
    assert result["seeds"] == 3
    assert result["total_generated_cases"] == 3000
    assert result["accepted_malicious"] == 0
    assert result["unanalysed"] == 0
