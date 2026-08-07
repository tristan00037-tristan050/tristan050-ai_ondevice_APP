"""Independent validator for the AC-25 R6 v4.1 evidence bundle."""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Optional

from . import output_containment
from . import strict_receipt as sr


RECEIPT_REQUIRED = (
    "schema_version", "repository", "pr_number", "start_head_sha",
    "start_head_tree", "target_head_sha", "target_head_tree",
    "pr_base_sha_observed", "run_id", "run_attempt", "exact_head_job_id",
    "run_started_at", "run_completed_at", "receipt_issued_at",
    "workflow_blob_oid", "command_plan_sha256", "guard_manifest_sha256",
    "changed_path_manifest_sha256", "dirty_path_manifest_sha256",
    "failing_guard_keys_sha256", "junit_manifest_sha256",
    "tap_manifest_sha256", "required_checks_sha256",
    "observed_checks_sha256", "provenance_sha256", "receipt_outcome",
    "gates", "ac25_pass",
)
GATE_KEYS = ("mb01", "mb02", "mb03", "mb04", "mb05", "remote_binding")


@dataclass(frozen=True)
class ValidationResult:
    valid: bool
    error_code: str
    ac25_pass: bool = False
    remote_binding: str = "NOT_RUN"


def _run_git(repository: Path, argv: list[str], *, binary: bool = False):
    try:
        code, stdout, _stderr = output_containment.run_and_read(
            ["git", "-C", str(repository), *argv], cwd=repository,
        )
    except (OSError, output_containment.ContainmentError) as exc:
        raise sr.StrictReceiptError("GIT_UNAVAILABLE") from exc
    if code != 0:
        raise sr.StrictReceiptError("GIT_QUERY_FAILED")
    return stdout if binary else stdout.decode("ascii", "strict").strip()


def _utc(value: str) -> datetime:
    if not isinstance(value, str) or sr.UTC_RE.fullmatch(value) is None:
        raise sr.StrictReceiptError("TIMESTAMP_INVALID")
    try:
        parsed = datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    except ValueError as exc:
        raise sr.StrictReceiptError("TIMESTAMP_INVALID") from exc
    if parsed.strftime("%Y-%m-%dT%H:%M:%SZ") != value:
        raise sr.StrictReceiptError("TIMESTAMP_INVALID")
    return parsed


def _digest_or_unknown(value: str, *, allow_unknown: bool = False):
    if allow_unknown and value == "UNKNOWN":
        return
    if not isinstance(value, str) or sr.SHA256_RE.fullmatch(value) is None:
        raise sr.StrictReceiptError("DIGEST_FIELD_INVALID")


def _validate_receipt(receipt: dict) -> None:
    sr._exact_object(receipt, RECEIPT_REQUIRED)
    if receipt["schema_version"] != sr.SCHEMA_VERSION:
        raise sr.StrictReceiptError("SCHEMA_VERSION_INVALID")
    if receipt["repository"] != "tristan00037-tristan050/tristan050-ai_ondevice_APP":
        raise sr.StrictReceiptError("REPOSITORY_INVALID")
    sr._nonnegative_int(receipt["pr_number"])
    for key in ("start_head_sha", "start_head_tree", "target_head_sha", "target_head_tree", "pr_base_sha_observed", "workflow_blob_oid"):
        if not isinstance(receipt[key], str) or sr.OID_RE.fullmatch(receipt[key]) is None:
            raise sr.StrictReceiptError("OID_INVALID")
    for key in ("run_id", "run_attempt", "exact_head_job_id"):
        if not isinstance(receipt[key], str) or sr.DECIMAL_RE.fullmatch(receipt[key]) is None:
            raise sr.StrictReceiptError("DECIMAL_ID_INVALID")
    if receipt["run_attempt"] == "0":
        raise sr.StrictReceiptError("RUN_ATTEMPT_INVALID")
    for key in (
        "command_plan_sha256", "guard_manifest_sha256", "changed_path_manifest_sha256",
        "dirty_path_manifest_sha256", "failing_guard_keys_sha256",
        "junit_manifest_sha256", "tap_manifest_sha256", "observed_checks_sha256",
        "provenance_sha256",
    ):
        _digest_or_unknown(receipt[key])
    _digest_or_unknown(receipt["required_checks_sha256"], allow_unknown=True)
    started = _utc(receipt["run_started_at"])
    completed = _utc(receipt["run_completed_at"])
    issued = _utc(receipt["receipt_issued_at"])
    if not started <= completed:
        raise sr.StrictReceiptError("RUN_TIME_ORDER_INVALID")
    if issued < completed:
        raise sr.StrictReceiptError("RECEIPT_ISSUED_BEFORE_RUN_COMPLETION")
    if receipt["receipt_outcome"] not in ("PASS", "FAIL"):
        raise sr.StrictReceiptError("RECEIPT_OUTCOME_INVALID")
    sr._exact_object(receipt["gates"], GATE_KEYS)
    if any(not isinstance(receipt["gates"][key], bool) for key in GATE_KEYS):
        raise sr.StrictReceiptError("GATE_STATE_INVALID")
    if not isinstance(receipt["ac25_pass"], bool):
        raise sr.StrictReceiptError("AC25_PASS_INVALID")
    every_gate = all(receipt["gates"].values())
    if receipt["ac25_pass"] != (receipt["receipt_outcome"] == "PASS" and every_gate):
        raise sr.StrictReceiptError("AC25_PASS_CONTRADICTORY")


def _validate_json_evidence(root: Path, receipt: dict, repository: Path) -> None:
    changed, changed_raw = sr.load_canonical_json(root / "changed_paths.json")
    changed_paths = sr.validate_changed_paths(
        changed, expected_base=receipt["start_head_sha"], expected_head=receipt["target_head_sha"]
    )
    if sr.sha256_bytes(changed_raw) != receipt["changed_path_manifest_sha256"]:
        raise sr.StrictReceiptError("CHANGED_PATH_MANIFEST_DIGEST_MISMATCH")
    git_raw = _run_git(
        repository,
        ["diff", "--name-only", "-z", receipt["start_head_sha"], receipt["target_head_sha"]],
        binary=True,
    )
    if not git_raw.endswith(b"\0") and git_raw:
        raise sr.StrictReceiptError("GIT_CHANGED_PATH_BYTES_INVALID")
    try:
        git_paths = [part.decode("utf-8", "strict") for part in git_raw.split(b"\0") if part]
    except UnicodeDecodeError as exc:
        raise sr.StrictReceiptError("GIT_CHANGED_PATH_NOT_UTF8") from exc
    sr.validate_unique_paths(git_paths)
    if tuple(git_paths) != changed_paths:
        raise sr.StrictReceiptError("CHANGED_PATH_SET_MISMATCH")

    dirty, dirty_raw = sr.load_canonical_json(root / "dirty_paths.json")
    sr._exact_object(dirty, ("declared_policy", "raw_final_worktree_clean", "paths"))
    if dirty["declared_policy"] != "WAITING_ERRATUM_2":
        raise sr.StrictReceiptError("ERRATUM_POLICY_INVALID")
    if dirty["raw_final_worktree_clean"] not in ("YES", "NO", "NOT_EVALUATED"):
        raise sr.StrictReceiptError("RAW_CLEAN_STATE_INVALID")
    if not isinstance(dirty["paths"], list):
        raise sr.StrictReceiptError("DIRTY_PATHS_INVALID")
    path_names = []
    for entry in dirty["paths"]:
        sr._exact_object(entry, ("path", "phase", "plan_sha256", "head_blob_oid", "after_sha256", "mode", "status"))
        path_names.append(sr.validate_path(entry["path"]))
        for key in ("plan_sha256", "after_sha256"):
            if entry[key] != "NONE" and sr.SHA256_RE.fullmatch(entry[key] or "") is None:
                raise sr.StrictReceiptError("DIRTY_PATH_DIGEST_INVALID")
        if entry["head_blob_oid"] != "NONE" and sr.OID_RE.fullmatch(entry["head_blob_oid"] or "") is None:
            raise sr.StrictReceiptError("DIRTY_PATH_BLOB_INVALID")
        if not isinstance(entry["phase"], str) or not isinstance(entry["mode"], str) or not isinstance(entry["status"], str):
            raise sr.StrictReceiptError("DIRTY_PATH_FIELD_INVALID")
    sr.validate_unique_paths(path_names)
    if sr.sha256_bytes(dirty_raw) != receipt["dirty_path_manifest_sha256"]:
        raise sr.StrictReceiptError("DIRTY_PATH_MANIFEST_DIGEST_MISMATCH")

    guards, guard_raw = sr.load_canonical_json(root / "failing_guard_keys.json")
    sr._exact_object(guards, ("keys",))
    if not isinstance(guards["keys"], list) or any(
        not isinstance(key, str) or not re_full_guard(key) for key in guards["keys"]
    ):
        raise sr.StrictReceiptError("GUARD_MANIFEST_INVALID")
    if len(guards["keys"]) != len(set(guards["keys"])) or guards["keys"] != sorted(guards["keys"]):
        raise sr.StrictReceiptError("GUARD_MANIFEST_INVALID")
    guard_digest = sr.sha256_bytes(guard_raw)
    if guard_digest != receipt["failing_guard_keys_sha256"] or guard_digest != receipt["guard_manifest_sha256"]:
        raise sr.StrictReceiptError("GUARD_MANIFEST_DIGEST_MISMATCH")

    required, required_raw = sr.load_canonical_json(root / "required_checks.json")
    required_known = sr.validate_required_checks(required)
    if receipt["required_checks_sha256"] == "UNKNOWN":
        if required_known:
            raise sr.StrictReceiptError("REQUIRED_CHECKS_DIGEST_UNKNOWN_CONTRADICTORY")
    elif receipt["required_checks_sha256"] != sr.sha256_bytes(required_raw):
        raise sr.StrictReceiptError("REQUIRED_CHECKS_DIGEST_MISMATCH")

    observed, observed_raw = sr.load_canonical_json(root / "observed_checks.json")
    observed_success = sr.validate_observed_checks(observed)
    if observed["head_sha"] != receipt["target_head_sha"]:
        raise sr.StrictReceiptError("OBSERVED_CHECK_HEAD_MISMATCH")
    if receipt["observed_checks_sha256"] != sr.sha256_bytes(observed_raw):
        raise sr.StrictReceiptError("OBSERVED_CHECKS_DIGEST_MISMATCH")
    if receipt["gates"]["mb03"] != (required_known and observed_success):
        raise sr.StrictReceiptError("MB03_GATE_CONTRADICTORY")

    provenance, provenance_raw = sr.load_canonical_json(root / "provenance.json")
    _validate_provenance(provenance, receipt)
    if receipt["provenance_sha256"] != sr.sha256_bytes(provenance_raw):
        raise sr.StrictReceiptError("PROVENANCE_DIGEST_MISMATCH")


def re_full_guard(value: str) -> bool:
    import re
    return re.fullmatch(r"[A-Z][A-Z0-9_]{0,127}", value) is not None


def _validate_provenance(document: dict, receipt: dict) -> None:
    sr._exact_object(
        document,
        (
            "repository", "pr_number", "start_head_sha", "target_head_sha",
            "target_head_tree", "workflow_path", "workflow_blob_oid", "run_id",
            "run_attempt", "exact_head_job_id", "run_started_at",
            "run_completed_at", "receipt_issued_at", "approval_issued_at", "commands",
        ),
    )
    bindings = {
        "repository": receipt["repository"], "pr_number": receipt["pr_number"],
        "start_head_sha": receipt["start_head_sha"], "target_head_sha": receipt["target_head_sha"],
        "target_head_tree": receipt["target_head_tree"], "workflow_blob_oid": receipt["workflow_blob_oid"],
        "run_id": receipt["run_id"], "run_attempt": receipt["run_attempt"],
        "exact_head_job_id": receipt["exact_head_job_id"], "run_started_at": receipt["run_started_at"],
        "run_completed_at": receipt["run_completed_at"], "receipt_issued_at": receipt["receipt_issued_at"],
    }
    if any(document[key] != value for key, value in bindings.items()):
        raise sr.StrictReceiptError("PROVENANCE_BINDING_MISMATCH")
    sr.validate_path(document["workflow_path"])
    approval = document["approval_issued_at"]
    if approval is not None and _utc(approval) > _utc(receipt["run_started_at"]):
        raise sr.StrictReceiptError("APPROVAL_ISSUED_AFTER_RUN")
    if not isinstance(document["commands"], list) or len(document["commands"]) < 3:
        raise sr.StrictReceiptError("PROVENANCE_COMMANDS_INVALID")
    observed_argv = []
    for command in document["commands"]:
        sr._exact_object(command, ("argv", "exit_code"))
        if not isinstance(command["argv"], list) or not command["argv"] or not all(isinstance(x, str) and x for x in command["argv"]):
            raise sr.StrictReceiptError("PROVENANCE_COMMANDS_INVALID")
        if not isinstance(command["exit_code"], int) or isinstance(command["exit_code"], bool):
            raise sr.StrictReceiptError("PROVENANCE_COMMANDS_INVALID")
        observed_argv.append(command["argv"])
    test_root = "tests" + "/" + "box5" + "_" + "ac25"
    required_argv = (
        ["python3", "-S", "-c", "import ac25.repo_contract_runner, ac25.strict_receipt_validator"],
        ["python3", "-m", "pytest", "-q", test_root],
        ["node", "--test", test_root + "/publish_check.test.mjs"],
    )
    if any(argv not in observed_argv for argv in required_argv):
        raise sr.StrictReceiptError("PROVENANCE_COMMANDS_INVALID")


def _validate_git_binding(root: Path, receipt: dict, repository: Path) -> None:
    if _run_git(repository, ["rev-parse", f"{receipt['start_head_sha']}^{{commit}}"] ) != receipt["start_head_sha"]:
        raise sr.StrictReceiptError("START_HEAD_MISMATCH")
    if _run_git(repository, ["show", "-s", "--format=%T", receipt["start_head_sha"]]) != receipt["start_head_tree"]:
        raise sr.StrictReceiptError("START_TREE_MISMATCH")
    if _run_git(repository, ["rev-parse", f"{receipt['target_head_sha']}^{{commit}}"] ) != receipt["target_head_sha"]:
        raise sr.StrictReceiptError("TARGET_HEAD_MISMATCH")
    if _run_git(repository, ["show", "-s", "--format=%T", receipt["target_head_sha"]]) != receipt["target_head_tree"]:
        raise sr.StrictReceiptError("HEAD_TREE_MISMATCH")
    workflow_path = sr.loads_strict((root / "provenance.json").read_bytes())["workflow_path"]
    actual_blob = _run_git(repository, ["rev-parse", f"{receipt['target_head_sha']}:{workflow_path}"])
    if actual_blob != receipt["workflow_blob_oid"]:
        raise sr.StrictReceiptError("WORKFLOW_BLOB_MISMATCH")


class GitHubFetcher:
    def __init__(self, token: str) -> None:
        self.token = token

    def __call__(self, url: str):
        request = urllib.request.Request(
            url,
            headers={
                "Accept": "application/vnd.github+json",
                "Authorization": f"Bearer {self.token}",
                "X-GitHub-Api-Version": "2022-11-28",
                "User-Agent": "butler-ac25-strict-receipt-validator/1",
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=20) as response:
                return json.loads(response.read().decode("utf-8", "strict"))
        except (OSError, urllib.error.URLError, json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise sr.StrictReceiptError("REMOTE_BINDING_UNKNOWN") from exc


def validate_remote(receipt: dict, fetch: Callable[[str], dict]) -> None:
    api = "https://api.github.com/repos/" + receipt["repository"]
    try:
        pr = fetch(f"{api}/pulls/{receipt['pr_number']}")
        commit = fetch(f"{api}/git/commits/{receipt['target_head_sha']}")
        run = fetch(f"{api}/actions/runs/{receipt['run_id']}")
        job = fetch(f"{api}/actions/jobs/{receipt['exact_head_job_id']}")
    except sr.StrictReceiptError:
        raise
    except Exception as exc:
        raise sr.StrictReceiptError("REMOTE_BINDING_UNKNOWN") from exc
    if pr.get("head", {}).get("sha") != receipt["target_head_sha"]:
        raise sr.StrictReceiptError("REMOTE_PR_HEAD_MISMATCH")
    if commit.get("tree", {}).get("sha") != receipt["target_head_tree"]:
        raise sr.StrictReceiptError("REMOTE_HEAD_TREE_MISMATCH")
    if str(run.get("id")) != receipt["run_id"] or run.get("head_sha") != receipt["target_head_sha"]:
        raise sr.StrictReceiptError("REMOTE_RUN_MISMATCH")
    if str(run.get("run_attempt")) != receipt["run_attempt"]:
        raise sr.StrictReceiptError("RUN_ATTEMPT_MISMATCH")
    if str(job.get("id")) != receipt["exact_head_job_id"] or job.get("head_sha") != receipt["target_head_sha"]:
        raise sr.StrictReceiptError("REMOTE_JOB_MISMATCH")
    if str(job.get("run_id")) != receipt["run_id"] or str(job.get("run_attempt")) != receipt["run_attempt"]:
        raise sr.StrictReceiptError("RUN_ATTEMPT_MISMATCH")


def validate_bundle(
    root: Path, repository: Path, *, online: bool = False,
    fetch: Optional[Callable[[str], dict]] = None,
) -> ValidationResult:
    try:
        sr.verify_digest_manifest(root)
        receipt, _receipt_raw = sr.load_canonical_json(root / "receipt.json")
        _schema, _schema_raw = sr.load_canonical_json(root / "receipt.schema.json")
        _validate_receipt(receipt)
        junit_digest = sr.validate_test_manifest(root, "junit", sr.parse_junit, receipt_digest="")
        tap_digest = sr.validate_test_manifest(root, "tap", sr.parse_tap, receipt_digest="")
        if junit_digest != receipt["junit_manifest_sha256"]:
            raise sr.StrictReceiptError("JUNIT_MANIFEST_DIGEST_MISMATCH")
        if tap_digest != receipt["tap_manifest_sha256"]:
            raise sr.StrictReceiptError("TAP_MANIFEST_DIGEST_MISMATCH")
        _validate_json_evidence(root, receipt, repository)
        _validate_git_binding(root, receipt, repository)
        if online:
            if fetch is None:
                token = os.environ.get("GITHUB_TOKEN", "")
                if not token:
                    raise sr.StrictReceiptError("REMOTE_BINDING_UNKNOWN")
                fetch = GitHubFetcher(token)
            validate_remote(receipt, fetch)
        return ValidationResult(True, "OK", receipt["ac25_pass"], "PASS" if online else "NOT_RUN")
    except (sr.StrictReceiptError, FileNotFoundError) as exc:
        code = exc.code if isinstance(exc, sr.StrictReceiptError) else "RECEIPT_FILE_NOT_FOUND"
        return ValidationResult(False, code, False, "UNKNOWN" if online else "NOT_RUN")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--receipt-dir", required=True)
    parser.add_argument("--repository", required=True)
    parser.add_argument("--online", action="store_true")
    try:
        args = parser.parse_args(argv)
        result = validate_bundle(Path(args.receipt_dir), Path(args.repository), online=args.online)
    except BaseException:
        result = ValidationResult(False, "VALIDATOR_INTERNAL_ERROR")
    if result.valid:
        sys.stdout.write("VERDICT=1\nERROR_CODE=OK\n")
        return 0
    sys.stdout.write(f"VERDICT=0\nERROR_CODE={result.error_code}\n")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
