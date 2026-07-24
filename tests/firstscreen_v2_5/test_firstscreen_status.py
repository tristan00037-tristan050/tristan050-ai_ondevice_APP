from __future__ import annotations

import hashlib
import json

import pytest

from scripts.release.firstscreen_status import (
    EXPECTED_JOBS,
    StatusEvidenceError,
    build_status,
    render_markdown,
    validate_status,
)


HEAD = "a" * 40
TREE = "b" * 40


def evidence() -> tuple[dict, dict, dict]:
    pull_request = {"number": 868, "head": {"sha": HEAD}, "mergeable": True}
    workflow_run = {
        "id": 123456,
        "name": "firstscreen-v2-5-product-gate",
        "head_sha": HEAD,
        "status": "completed",
        "conclusion": "success",
    }
    jobs = {
        "total_count": 6,
        "jobs": [
            {
                "name": name,
                "status": "completed",
                "conclusion": "success",
                "head_sha": HEAD,
            }
            for name in EXPECTED_JOBS
        ],
    }
    return pull_request, workflow_run, jobs


def build(**overrides):
    pull_request, workflow_run, jobs = evidence()
    arguments = {
        "pull_request_raw": pull_request,
        "workflow_run_raw": workflow_run,
        "workflow_jobs_raw": jobs,
        "tree": TREE,
        "protected_changed_paths": 0,
        "fsv32_p0_01_pass": True,
        "fsv32_p0_02_pass": True,
    }
    arguments.update(overrides)
    return build_status(**arguments)


def test_status_and_markdown_share_one_validated_authority() -> None:
    status = build()
    assert validate_status(status) is status
    assert status["workflow_job_count"] == 6
    assert status["local_scope_merge_allowed"] is False
    markdown = render_markdown(status)
    assert HEAD in markdown
    assert TREE in markdown
    assert "123456" in markdown
    assert "6/6 success" in markdown


@pytest.mark.parametrize(
    "mutation",
    [
        lambda pr, run, jobs: jobs.update(total_count=0, jobs=[]),
        lambda pr, run, jobs: jobs["jobs"][0].update(conclusion="skipped"),
        lambda pr, run, jobs: jobs["jobs"][0].update(name="unrelated-green-job"),
        lambda pr, run, jobs: run.update(head_sha="c" * 40),
        lambda pr, run, jobs: run.update(conclusion=None),
        lambda pr, run, jobs: pr.update(mergeable=False),
    ],
)
def test_incomplete_or_unrelated_evidence_fails_closed(mutation) -> None:
    pull_request, workflow_run, jobs = evidence()
    mutation(pull_request, workflow_run, jobs)
    with pytest.raises(StatusEvidenceError):
        build_status(
            pull_request_raw=pull_request,
            workflow_run_raw=workflow_run,
            workflow_jobs_raw=jobs,
            tree=TREE,
            protected_changed_paths=0,
            fsv32_p0_01_pass=True,
            fsv32_p0_02_pass=True,
        )


def test_independent_reaudit_receipt_is_required_for_local_merge(tmp_path) -> None:
    payload = {
        "head": HEAD,
        "tree": TREE,
        "result": "PASS",
        "independent": True,
    }
    canonical = json.dumps(
        payload,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    receipt = {
        "schema_version": "butler.firstscreen.v3.2-r3.independent-reaudit.v1",
        "payload": payload,
        "payload_sha256": hashlib.sha256(canonical).hexdigest(),
    }
    path = tmp_path / "reaudit.json"
    path.write_text(json.dumps(receipt), encoding="utf-8")
    assert build(independent_reaudit_receipt=path)["local_scope_merge_allowed"] is True


def test_protected_scope_change_fails_closed() -> None:
    with pytest.raises(StatusEvidenceError, match="PROTECTED_SCOPE_CHANGED"):
        build(protected_changed_paths=1)
