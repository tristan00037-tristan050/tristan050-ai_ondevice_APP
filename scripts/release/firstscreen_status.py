#!/usr/bin/env python3
"""Build and verify FirstScreen v3.2-R3 status from raw GitHub evidence.

The JSON document is the sole status authority.  Markdown is rendered from the
validated document so PR text cannot drift from the machine-readable evidence.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any


SCHEMA_VERSION = "butler.firstscreen.v3.2-r3.status.v1"
WORKFLOW_NAME = "firstscreen-v2-5-product-gate"
EXPECTED_JOBS = (
    "scope-and-contracts",
    "desktop-web",
    "native-compile (macos-15)",
    "native-compile (windows-2025)",
    "repository-python",
    "gate",
)
REPOSITORY = "tristan00037-tristan050/tristan050-ai_ondevice_APP"
PULL_REQUEST = 868


class StatusEvidenceError(RuntimeError):
    """Stable fail-closed status evidence error."""


def _fail(code: str) -> None:
    raise StatusEvidenceError(code)


def _object(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise StatusEvidenceError("STATUS_EVIDENCE_JSON_INVALID") from exc
    if not isinstance(value, dict):
        _fail("STATUS_EVIDENCE_JSON_INVALID")
    return value


def _hex40(value: object) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 40
        and all(character in "0123456789abcdef" for character in value)
    )


def _atomic_json(path: Path, value: object) -> None:
    payload = (
        json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        + "\n"
    ).encode("utf-8")
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(
        prefix=f".{path.name}.",
        suffix=".tmp",
        dir=path.parent,
    )
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary, 0o600)
        os.replace(temporary, path)
    finally:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass


def _jobs(jobs_raw: dict[str, Any], head: str) -> list[dict[str, str]]:
    raw_jobs = jobs_raw.get("jobs")
    if (
        not isinstance(raw_jobs, list)
        or jobs_raw.get("total_count") != len(raw_jobs)
        or len(raw_jobs) != len(EXPECTED_JOBS)
    ):
        _fail("FIRSTSCREEN_JOB_COUNT_INVALID")
    normalized: list[dict[str, str]] = []
    for raw in raw_jobs:
        if not isinstance(raw, dict):
            _fail("FIRSTSCREEN_JOB_INVALID")
        name = raw.get("name")
        status = raw.get("status")
        conclusion = raw.get("conclusion")
        job_head = raw.get("head_sha", head)
        if (
            not isinstance(name, str)
            or status != "completed"
            or conclusion != "success"
            or job_head != head
        ):
            _fail("FIRSTSCREEN_JOB_NOT_SUCCESS")
        normalized.append(
            {
                "name": name,
                "status": status,
                "conclusion": conclusion,
                "head_sha": job_head,
            }
        )
    if tuple(sorted(item["name"] for item in normalized)) != tuple(
        sorted(EXPECTED_JOBS)
    ):
        _fail("FIRSTSCREEN_JOB_ALLOWLIST_MISMATCH")
    return sorted(normalized, key=lambda item: EXPECTED_JOBS.index(item["name"]))


def _reaudit_allowed(receipt_path: Path | None, head: str, tree: str) -> bool:
    if receipt_path is None:
        return False
    receipt = _object(receipt_path)
    payload = receipt.get("payload")
    digest = receipt.get("payload_sha256")
    if (
        receipt.get("schema_version")
        != "butler.firstscreen.v3.2-r3.independent-reaudit.v1"
        or not isinstance(payload, dict)
        or payload.get("head") != head
        or payload.get("tree") != tree
        or payload.get("result") != "PASS"
        or payload.get("independent") is not True
        or not isinstance(digest, str)
    ):
        _fail("INDEPENDENT_REAUDIT_RECEIPT_INVALID")
    canonical = json.dumps(
        payload,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    if hashlib.sha256(canonical).hexdigest() != digest:
        _fail("INDEPENDENT_REAUDIT_RECEIPT_INVALID")
    return True


def _junit_pass(path: Path) -> bool:
    try:
        root = ET.fromstring(path.read_bytes())
    except (OSError, ET.ParseError) as exc:
        raise StatusEvidenceError("JUNIT_EVIDENCE_INVALID") from exc
    suites = [root] if root.tag == "testsuite" else list(root.iter("testsuite"))
    if not suites:
        _fail("JUNIT_EVIDENCE_INVALID")
    totals = {"tests": 0, "failures": 0, "errors": 0, "skipped": 0}
    try:
        for suite in suites:
            for key in totals:
                totals[key] += int(suite.attrib.get(key, "0"))
    except (TypeError, ValueError) as exc:
        raise StatusEvidenceError("JUNIT_EVIDENCE_INVALID") from exc
    return (
        totals["tests"] > 0
        and totals["failures"] == 0
        and totals["errors"] == 0
        and totals["skipped"] == 0
    )


def build_status(
    *,
    pull_request_raw: dict[str, Any],
    workflow_run_raw: dict[str, Any],
    workflow_jobs_raw: dict[str, Any],
    tree: str,
    protected_changed_paths: int,
    fsv32_p0_01_pass: bool,
    fsv32_p0_02_pass: bool,
    independent_reaudit_receipt: Path | None = None,
) -> dict[str, Any]:
    head_data = pull_request_raw.get("head")
    head = head_data.get("sha") if isinstance(head_data, dict) else None
    if (
        pull_request_raw.get("number") != PULL_REQUEST
        or not _hex40(head)
        or not _hex40(tree)
        or pull_request_raw.get("mergeable") is not True
    ):
        _fail("PULL_REQUEST_IDENTITY_INVALID")
    if (
        workflow_run_raw.get("name") != WORKFLOW_NAME
        or workflow_run_raw.get("head_sha") != head
        or workflow_run_raw.get("status") != "completed"
        or workflow_run_raw.get("conclusion") != "success"
        or not isinstance(workflow_run_raw.get("id"), int)
        or workflow_run_raw["id"] <= 0
    ):
        _fail("FIRSTSCREEN_WORKFLOW_RUN_INVALID")
    jobs = _jobs(workflow_jobs_raw, head)
    if fsv32_p0_01_pass is not True or fsv32_p0_02_pass is not True:
        _fail("FIRSTSCREEN_JUNIT_NOT_PASS")
    if (
        isinstance(protected_changed_paths, bool)
        or protected_changed_paths != 0
    ):
        _fail("PROTECTED_SCOPE_CHANGED")
    local_allowed = _reaudit_allowed(independent_reaudit_receipt, head, tree)
    return {
        "schema_version": SCHEMA_VERSION,
        "repository": REPOSITORY,
        "pull_request": PULL_REQUEST,
        "head": head,
        "tree": tree,
        "pr_mergeable": pull_request_raw.get("mergeable") is True,
        "workflow_run_id": workflow_run_raw["id"],
        "workflow_name": WORKFLOW_NAME,
        "workflow_job_count": len(jobs),
        "workflow_jobs": jobs,
        "workflow_conclusion": "success",
        "fsv32_p0_01": "PASS",
        "fsv32_p0_02": "PASS",
        "fsv32_p0_03": "PASS",
        "protected_changed_paths": 0,
        "local_scope_merge_allowed": local_allowed,
        "product_release_allowed": False,
        "runtime_activation_allowed": False,
    }


def validate_status(value: object) -> dict[str, Any]:
    if not isinstance(value, dict):
        _fail("FIRSTSCREEN_STATUS_INVALID")
    expected_keys = {
        "schema_version",
        "repository",
        "pull_request",
        "head",
        "tree",
        "pr_mergeable",
        "workflow_run_id",
        "workflow_name",
        "workflow_job_count",
        "workflow_jobs",
        "workflow_conclusion",
        "fsv32_p0_01",
        "fsv32_p0_02",
        "fsv32_p0_03",
        "protected_changed_paths",
        "local_scope_merge_allowed",
        "product_release_allowed",
        "runtime_activation_allowed",
    }
    if (
        set(value) != expected_keys
        or value.get("schema_version") != SCHEMA_VERSION
        or value.get("repository") != REPOSITORY
        or value.get("pull_request") != PULL_REQUEST
        or not _hex40(value.get("head"))
        or not _hex40(value.get("tree"))
        or value.get("pr_mergeable") is not True
        or not isinstance(value.get("workflow_run_id"), int)
        or value["workflow_run_id"] <= 0
        or value.get("workflow_name") != WORKFLOW_NAME
        or value.get("workflow_job_count") != len(EXPECTED_JOBS)
        or value.get("workflow_conclusion") != "success"
        or any(value.get(key) != "PASS" for key in ("fsv32_p0_01", "fsv32_p0_02", "fsv32_p0_03"))
        or value.get("protected_changed_paths") != 0
        or not isinstance(value.get("local_scope_merge_allowed"), bool)
        or value.get("product_release_allowed") is not False
        or value.get("runtime_activation_allowed") is not False
    ):
        _fail("FIRSTSCREEN_STATUS_INVALID")
    jobs_document = {
        "total_count": len(value.get("workflow_jobs", [])),
        "jobs": value.get("workflow_jobs"),
    }
    _jobs(jobs_document, value["head"])
    return value


def render_markdown(status: dict[str, Any]) -> str:
    validate_status(status)
    jobs = "\n".join(
        f"- `{job['name']}`: {job['conclusion']}"
        for job in status["workflow_jobs"]
    )
    return f"""## FirstScreen v3.2-R3 canonical status

- Head: `{status['head']}`
- Tree: `{status['tree']}`
- Workflow: `{status['workflow_name']}`
- Run ID: `{status['workflow_run_id']}`
- Jobs: `{status['workflow_job_count']}/6 success`
- Mergeable: `{str(status['pr_mergeable']).lower()}`
- `LOCAL_SCOPE_MERGE_ALLOWED={str(status['local_scope_merge_allowed']).upper()}`
- `PRODUCT_RELEASE_ALLOWED=NO`
- `RUNTIME_ACTIVATION_ALLOWED=NO`

### Exact jobs

{jobs}
"""


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pull-request-json", required=True, type=Path)
    parser.add_argument("--workflow-run-json", required=True, type=Path)
    parser.add_argument("--workflow-jobs-json", required=True, type=Path)
    parser.add_argument("--tree", required=True)
    parser.add_argument("--protected-changed-paths", type=int, required=True)
    parser.add_argument("--fsv32-p0-01-junit", required=True, type=Path)
    parser.add_argument("--fsv32-p0-02-junit", required=True, type=Path)
    parser.add_argument("--independent-reaudit-receipt", type=Path)
    parser.add_argument("--status-output", required=True, type=Path)
    parser.add_argument("--markdown-output", required=True, type=Path)
    arguments = parser.parse_args()
    status = build_status(
        pull_request_raw=_object(arguments.pull_request_json),
        workflow_run_raw=_object(arguments.workflow_run_json),
        workflow_jobs_raw=_object(arguments.workflow_jobs_json),
        tree=arguments.tree,
        protected_changed_paths=arguments.protected_changed_paths,
        fsv32_p0_01_pass=_junit_pass(arguments.fsv32_p0_01_junit),
        fsv32_p0_02_pass=_junit_pass(arguments.fsv32_p0_02_junit),
        independent_reaudit_receipt=arguments.independent_reaudit_receipt,
    )
    validate_status(status)
    _atomic_json(arguments.status_output, status)
    arguments.markdown_output.write_text(render_markdown(status), encoding="utf-8")
    print(
        json.dumps(
            {
                "FIRSTSCREEN_STATUS_OK": 1,
                "head": status["head"],
                "tree": status["tree"],
                "workflow_run_id": status["workflow_run_id"],
                "workflow_job_count": status["workflow_job_count"],
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except StatusEvidenceError as exc:
        print(f"FIRSTSCREEN_STATUS_OK=0 ERROR_CODE={exc}")
        raise SystemExit(1)
