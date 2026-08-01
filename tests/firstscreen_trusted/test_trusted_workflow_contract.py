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
    # 판정값 게시기는 인라인 heredoc 에서 보호 자산 파일로 추출됐다. 구조적 불변
    # 리터럴은 이제 그 스크립트에 있으며, 워크플로는 그 스크립트를 호출한다.
    # 주석이 아니라 실제 실행 명령을 검사한다: 호출 라인이 지워지면(주석만 남아도)
    # fail-closed 되도록, 앞이 '#' 이 아닌 python3 호출 라인을 요구한다.
    assert re.search(
        r"(?m)^\s*python3 scripts/ci/publish_trusted_verdict\.py\b",
        text,
    ), "publisher must be invoked (not merely mentioned in a comment)"
    verdict = (
        ROOT / "scripts/ci/publish_trusted_verdict.py"
    ).read_text(encoding="utf-8")
    assert "PR_CODE_EXECUTED_BY_TRUSTED_VERIFIER=0" in verdict


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


def test_trusted_workflow_installs_hash_locked_dependencies() -> None:
    text = WORKFLOW.read_text(encoding="utf-8")
    assert "pip install --require-hashes" in text
    assert "-r requirements-firstscreen-ci.lock" in text


def test_regression_failures_emit_only_fixed_verdicts() -> None:
    text = WORKFLOW.read_text(encoding="utf-8")
    assert '>"${python_log}" 2>&1' in text
    assert '>"${node_log}" 2>&1' in text
    assert "TRUSTED_PYTHON_REGRESSION_FAILED" in text
    assert "TRUSTED_NODE_REGRESSION_FAILED" in text
    assert 'cat "${python_log}"' not in text
    assert 'cat "${node_log}"' not in text


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
