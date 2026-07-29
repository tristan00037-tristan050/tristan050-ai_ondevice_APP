from __future__ import annotations

import json
import re
from pathlib import Path

import pytest


pytestmark = pytest.mark.no_sidecar_token

ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = ROOT / ".github/workflows/firstscreen-learning-trusted-verifier.yml"
PRODUCER = ROOT / ".github/workflows/firstscreen-v2-5.yml"


def test_trusted_workflow_uses_default_branch_code_and_raw_artifact_data() -> None:
    text = WORKFLOW.read_text(encoding="utf-8")
    assert "workflow_run:" in text
    assert "workflows: [firstscreen-v2-5-product-gate]" in text
    assert "pull_request_target" not in text
    assert "ref: ${{ github.sha }}" in text
    assert "actions/download-artifact@" not in text
    assert "trusted_firstscreen_run.py" in text
    assert "trusted_firstscreen_artifact.py" in text
    assert "npm ci" not in text
    assert "saxes" not in text
    assert "source/source.zip" not in text
    assert "PR_CODE_EXECUTED_BY_TRUSTED_VERIFIER=0" in text


def test_trusted_workflow_has_read_only_permissions_and_no_attestation_path() -> None:
    text = WORKFLOW.read_text(encoding="utf-8")
    permissions = re.search(
        r"permissions:\n(?P<body>(?:  [^\n]+\n)+)",
        text,
    )
    assert permissions is not None
    assert permissions.group("body").splitlines() == [
        "  actions: read",
        "  contents: read",
        "  pull-requests: read",
    ]
    combined = text + PRODUCER.read_text(encoding="utf-8")
    forbidden = (
        "id-token: write",
        "attestations: write",
        "attest-build-provenance",
        "gh attestation verify",
    )
    assert all(value not in combined for value in forbidden)


def test_all_actions_are_full_commit_pins_and_recorded() -> None:
    text = WORKFLOW.read_text(encoding="utf-8")
    used = re.findall(r"uses: ([A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+)@([0-9a-f]{40})", text)
    assert used
    assert len(re.findall(r"uses:", text)) == len(used)
    pins = json.loads(
        (
            ROOT / "butler-desktop/acceptance/action-pins.v1.json"
        ).read_text(encoding="utf-8")
    )
    recorded = {
        (item["repository"], item["resolved_commit_sha"])
        for item in pins["actions"]
    }
    assert set(used) <= recorded


def test_protected_manifest_has_exact_v3_cardinality() -> None:
    manifest = json.loads(
        (
            ROOT / "butler-desktop/acceptance/required-tests.v3.json"
        ).read_text(encoding="utf-8")
    )
    assert manifest["schema_version"] == 3
    assert manifest["normative_required"] == 90
    assert manifest["supplemental_required"] == 2
    assert manifest["required_total"] == 92
    assert len(manifest["tests"]) == 92
    assert len({item["id"] for item in manifest["tests"]}) == 92
