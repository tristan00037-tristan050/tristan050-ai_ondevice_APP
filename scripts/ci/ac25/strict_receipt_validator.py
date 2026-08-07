"""Independent AC-25 R6 v4.2 delivery and receipt verifier.

The receipt is data, never authority.  Every acceptance gate is recomputed
from digest-bound raw evidence, Git objects, delivery bytes, and (for the gate
command) live GitHub state.
"""
from __future__ import annotations

import argparse
import fnmatch
import json
import os
import re
import sys
import tempfile
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Optional

from . import delivery_manifest as dm
from . import output_containment
from . import receipt_schema
from . import strict_receipt as sr


REPOSITORY = "tristan00037-tristan050/tristan050-ai_ondevice_APP"
PR_NUMBER = 904
BASE_BRANCH = "main"
WORKFLOW_ID = 328222782
WORKFLOW_PATH = ".github/workflows/box5-ac25-stage-a-smoke.yml"
EXACT_HEAD_JOB_NAME = "ac25-repo-contracts-exact-head"
ERRATUM_PATH = "docs/box5/ac25/ac25-r6-erratum-2.json"
ERRATUM_SHA256 = "2ed584f139227a454c821729c44586fd628d8f0239b61700fae62cc7d7c185db"
RECEIPT_SCHEMA_SHA256 = "94bb246403f182dc2f2d603eda8a9711125c143b0545d58b51a6021ae312d96a"
RECEIPT_DIRNAME = "AC25_R6_CLOSE_RECEIPT"
CANDIDATE_REF = "refs/heads/feat/box5-ac25-trusted-verification"
SELF_ASSERTED_FIELDS = frozenset({"gates", "receipt_outcome", "ac25_pass"})
TEST_ROOT = "tests" + "/" + "box5" + "_" + "ac25"
CLEAN_STATUS_COMMAND = (
    "git", "status", "--porcelain=v2", "-z", "--untracked-files=all",
)
REQUIRED_COMMANDS = (
    ("python3", "-S", "-c", "import ac25.repo_contract_runner, ac25.strict_receipt_validator"),
    ("python3", "-m", "pytest", "-q", TEST_ROOT),
    ("node", "--test", TEST_ROOT + "/publish_check.test.mjs"),
    CLEAN_STATUS_COMMAND,
)


class GateFailure(Exception):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


@dataclass(frozen=True)
class ValidationResult:
    receipt_valid: bool
    evidence_valid: bool
    remote_binding: str
    ac25_pass: bool
    error_code: str

    @property
    def valid(self) -> bool:
        return self.receipt_valid and self.evidence_valid


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


def _run_command(argv: list[str], *, cwd: Path, env: Optional[dict] = None) -> tuple[int, bytes]:
    try:
        code, out, _err = output_containment.run_and_read(argv, cwd=cwd, env=env)
    except (OSError, output_containment.ContainmentError) as exc:
        raise sr.StrictReceiptError("COMMAND_UNAVAILABLE") from exc
    return code, out


def _git(repository: Path, argv: list[str], *, binary: bool = False) -> bytes | str:
    code, out = _run_command(["git", "-C", str(repository), *argv], cwd=repository)
    if code != 0:
        raise sr.StrictReceiptError("GIT_QUERY_FAILED")
    if binary:
        return out
    try:
        return out.decode("ascii", "strict").strip()
    except UnicodeDecodeError as exc:
        raise sr.StrictReceiptError("GIT_OUTPUT_INVALID") from exc


def _load_json(root: Path, name: str, receipt: dict, digest_key: str):
    document, raw = sr.load_canonical_json(root / name)
    if sr.sha256_bytes(raw) != receipt[digest_key]:
        raise sr.StrictReceiptError("EVIDENCE_DIGEST_MISMATCH")
    return document, raw


def _validate_receipt_schema(root: Path, receipt: dict) -> None:
    if SELF_ASSERTED_FIELDS & set(receipt):
        raise sr.StrictReceiptError("SELF_ASSERTED_GATE_MISMATCH")
    try:
        schema_raw = (root / "receipt.schema.json").read_bytes()
        if sr.sha256_bytes(schema_raw) != RECEIPT_SCHEMA_SHA256:
            raise sr.StrictReceiptError("RECEIPT_SCHEMA_DIGEST_MISMATCH")
        schema = sr.loads_strict(schema_raw)
    except FileNotFoundError as exc:
        raise sr.StrictReceiptError("RECEIPT_SCHEMA_MISSING") from exc
    receipt_schema.validate(receipt, schema)
    started = _utc(receipt["run_started_at"])
    completed = _utc(receipt["run_completed_at"])
    issued = _utc(receipt["receipt_issued_at"])
    if started > completed or issued < completed:
        raise sr.StrictReceiptError("RUN_TIME_ORDER_INVALID")


def _validate_contract(root: Path, receipt: dict) -> Optional[str]:
    evidence, _raw = _load_json(root, "contract_evidence.json", receipt, "contract_evidence_sha256")
    sr._exact_object(
        evidence,
        (
            "target_head_sha", "command_plan_sha256", "expected_inventory",
            "expected_inventory_sha256", "process_exit_code",
            "primary_failed_guard", "parse_error_code", "observed_guards",
            "failing_guard_keys",
        ),
    )
    if (
        evidence["target_head_sha"] != receipt["target_head_sha"]
        or evidence["command_plan_sha256"] != receipt["command_plan_sha256"]
        or evidence["expected_inventory_sha256"] != receipt["expected_guard_inventory_sha256"]
    ):
        raise sr.StrictReceiptError("CONTRACT_BINDING_MISMATCH")
    expected = evidence["expected_inventory"]
    observed = evidence["observed_guards"]
    failing = evidence["failing_guard_keys"]
    if not isinstance(expected, list) or not all(
        isinstance(key, str) and re.fullmatch(r"[A-Z][A-Z0-9_]{0,127}", key)
        for key in expected
    ):
        raise sr.StrictReceiptError("CONTRACT_INVENTORY_INVALID")
    if expected != sorted(set(expected)):
        raise sr.StrictReceiptError("CONTRACT_INVENTORY_INVALID")
    bound = sr.canonical_json_bytes({
        "guards": expected, "target_head_sha": receipt["target_head_sha"],
    })
    if sr.sha256_bytes(bound) != evidence["expected_inventory_sha256"]:
        raise sr.StrictReceiptError("CONTRACT_INVENTORY_BINDING_MISMATCH")
    if not isinstance(observed, dict) or any(
        not isinstance(key, str) or value not in ("0", "1")
        for key, value in observed.items()
    ):
        raise sr.StrictReceiptError("CONTRACT_OBSERVATION_INVALID")
    if set(observed) != set(expected):
        return "CONTRACT_INVENTORY_MISMATCH" if expected else "CONTRACT_INVENTORY_EMPTY"
    computed_failing = sorted(key for key, value in observed.items() if value != "1")
    if not isinstance(failing, list) or failing != computed_failing:
        raise sr.StrictReceiptError("CONTRACT_FAILURE_SET_MISMATCH")
    if not expected:
        return "CONTRACT_INVENTORY_EMPTY"
    if evidence["parse_error_code"] != "NONE":
        return "CONTRACT_PARSE_FAILED"
    if evidence["process_exit_code"] != 0:
        return "CONTRACT_PROCESS_FAILED"
    if evidence["primary_failed_guard"] != "NONE":
        return "CONTRACT_PRIMARY_FAILURE"
    if computed_failing:
        return "CONTRACT_GUARDS_FAILED"
    return None


def _validate_clean(root: Path, receipt: dict, repository: Path) -> Optional[str]:
    evidence, _raw = _load_json(root, "clean_check.json", receipt, "clean_check_sha256")
    sr._exact_object(
        evidence,
        (
            "target_head_sha", "erratum_2_sha256", "clean_check_executed",
            "git_status_exit_code", "raw_status_path", "raw_status_sha256",
            "raw_final_worktree_clean", "dirty_path_count",
            "outside_proposed_set_count", "post_run_cleanup_used",
            "output_root_location",
        ),
    )
    if evidence["target_head_sha"] != receipt["target_head_sha"]:
        raise sr.StrictReceiptError("CLEAN_CHECK_BINDING_MISMATCH")
    if evidence["erratum_2_sha256"] != ERRATUM_SHA256 or receipt["erratum_2_sha256"] != ERRATUM_SHA256:
        return "ERRATUM_2_DIGEST_MISMATCH"
    erratum = _git(repository, ["show", f"{receipt['target_head_sha']}:{ERRATUM_PATH}"], binary=True)
    if sr.sha256_bytes(erratum) != ERRATUM_SHA256:
        return "ERRATUM_2_DIGEST_MISMATCH"
    if evidence["raw_status_path"] != "clean-status.porcelain-v2.z":
        raise sr.StrictReceiptError("CLEAN_CHECK_RAW_PATH_INVALID")
    raw = (root / evidence["raw_status_path"]).read_bytes()
    if sr.sha256_bytes(raw) != evidence["raw_status_sha256"]:
        raise sr.StrictReceiptError("CLEAN_CHECK_RAW_DIGEST_MISMATCH")
    if evidence["post_run_cleanup_used"] is not False:
        return "POST_RUN_CLEANUP_FORBIDDEN"
    if evidence["output_root_location"] != "OUTSIDE_REPOSITORY_ONLY":
        return "OUTPUT_ROOT_POLICY_VIOLATION"
    if evidence["clean_check_executed"] is not True or evidence["git_status_exit_code"] != 0:
        return "CLEAN_CHECK_NOT_SUCCESS"
    clean = raw == b""
    if evidence["raw_final_worktree_clean"] is not clean:
        raise sr.StrictReceiptError("CLEAN_CHECK_SELF_REPORT_MISMATCH")
    if evidence["dirty_path_count"] != (0 if clean else len(raw.split(b"\0")) - 1):
        raise sr.StrictReceiptError("CLEAN_CHECK_COUNT_MISMATCH")
    if not clean or evidence["outside_proposed_set_count"] != 0:
        return "RAW_FINAL_WORKTREE_DIRTY"
    return None


def _validate_changed_paths(delivery: Path, root: Path, receipt: dict, repository: Path) -> None:
    changed, changed_raw = _load_json(root, "changed_paths.json", receipt, "changed_path_manifest_sha256")
    paths = sr.validate_changed_paths(
        changed, expected_base=receipt["start_head_sha"], expected_head=receipt["target_head_sha"],
    )
    if (delivery / "changed_paths.json").read_bytes() != changed_raw:
        raise sr.StrictReceiptError("CHANGED_PATH_MANIFEST_ROOT_MISMATCH")
    git_raw = _git(
        repository,
        ["diff", "--name-only", "-z", "--no-renames", receipt["start_head_sha"], receipt["target_head_sha"]],
        binary=True,
    )
    if git_raw != (delivery / "changed_paths.nul").read_bytes():
        raise sr.StrictReceiptError("CHANGED_PATH_NUL_MISMATCH")
    try:
        actual = tuple(part.decode("utf-8", "strict") for part in git_raw.split(b"\0") if part)
    except UnicodeDecodeError as exc:
        raise sr.StrictReceiptError("GIT_CHANGED_PATH_NOT_UTF8") from exc
    if actual != paths:
        raise sr.StrictReceiptError("CHANGED_PATH_SET_MISMATCH")


def _validate_checks(root: Path, receipt: dict) -> tuple[Optional[str], dict, dict]:
    required, _ = _load_json(root, "required_checks.json", receipt, "required_checks_sha256")
    observed, _ = _load_json(root, "observed_checks.json", receipt, "observed_checks_sha256")
    if observed.get("head_sha") != receipt["target_head_sha"]:
        raise sr.StrictReceiptError("OBSERVED_CHECK_HEAD_MISMATCH")
    try:
        required_ids = sr.validate_required_checks(required)
        observed_map = sr.validate_observed_checks(observed)
        sr.require_successful_checks(required_ids, observed_map)
    except sr.StrictReceiptError as exc:
        if exc.code in {
            "REQUIRED_CHECK_SET_EMPTY", "REQUIRED_CHECK_MISSING",
            "REQUIRED_CHECK_APP_ID_MISMATCH", "REQUIRED_CHECK_NOT_SUCCESS",
            "REQUIRED_CHECKS_INCOMPLETE", "REQUIRED_CHECKS_PAGINATION_INCOMPLETE",
            "OBSERVED_CHECKS_INCOMPLETE",
        }:
            return exc.code, required, observed
        raise
    return None, required, observed


def _validate_tests(root: Path, receipt: dict) -> Optional[str]:
    junit_digest = sr.validate_test_manifest(root, "junit", sr.parse_junit, receipt_digest="")
    tap_digest = sr.validate_test_manifest(root, "tap", sr.parse_tap, receipt_digest="")
    if junit_digest != receipt["junit_manifest_sha256"]:
        raise sr.StrictReceiptError("JUNIT_MANIFEST_DIGEST_MISMATCH")
    if tap_digest != receipt["tap_manifest_sha256"]:
        raise sr.StrictReceiptError("TAP_MANIFEST_DIGEST_MISMATCH")
    junit, _ = sr.load_canonical_json(root / "junit/manifest.json")
    tap, _ = sr.load_canonical_json(root / "tap/manifest.json")
    js = junit["summary"]
    ts = tap["summary"]
    if js["failures"] != 0 or js["errors"] != 0 or js["skipped"] != 0:
        return "JUNIT_NOT_SUCCESS"
    if ts["not_ok"] != 0 or ts["todo"] != 0 or ts["skipped"] != 0:
        return "TAP_NOT_SUCCESS"
    expected_files = set(sr.ROOT_FILES)
    expected_files.update(entry["path"] for entry in junit["files"])
    expected_files.update(entry["path"] for entry in tap["files"])
    if set(sr._all_files(root)) != expected_files:
        raise sr.StrictReceiptError("RECEIPT_LAYOUT_INVALID")
    return None


def _validate_provenance(root: Path, receipt: dict) -> tuple[Optional[str], dict]:
    document, _raw = _load_json(root, "provenance.json", receipt, "provenance_sha256")
    sr._exact_object(
        document,
        (
            "repository", "pr_number", "start_head_sha", "target_head_sha",
            "target_head_tree", "workflow_id", "workflow_path", "workflow_blob_oid",
            "run_id", "run_attempt", "run_status", "run_conclusion", "run_event",
            "exact_head_job_id", "job_name", "job_status", "job_conclusion",
            "job_run_id", "job_head_sha", "job_attempt", "run_started_at",
            "run_completed_at", "receipt_issued_at", "commands",
            "clean_check_command_index",
        ),
    )
    bindings = {
        "repository": receipt["repository"], "pr_number": receipt["pr_number"],
        "start_head_sha": receipt["start_head_sha"], "target_head_sha": receipt["target_head_sha"],
        "target_head_tree": receipt["target_head_tree"], "workflow_id": receipt["workflow_id"],
        "workflow_path": receipt["workflow_path"], "workflow_blob_oid": receipt["workflow_blob_oid"],
        "run_id": receipt["run_id"], "run_attempt": receipt["run_attempt"],
        "exact_head_job_id": receipt["exact_head_job_id"],
        "run_started_at": receipt["run_started_at"], "run_completed_at": receipt["run_completed_at"],
        "receipt_issued_at": receipt["receipt_issued_at"],
    }
    if any(document.get(key) != value for key, value in bindings.items()):
        raise sr.StrictReceiptError("PROVENANCE_BINDING_MISMATCH")
    if document["job_name"] != EXACT_HEAD_JOB_NAME:
        raise sr.StrictReceiptError("PROVENANCE_JOB_NAME_MISMATCH")
    if (
        document["job_run_id"] != receipt["run_id"]
        or document["job_head_sha"] != receipt["target_head_sha"]
        or document["job_attempt"] != receipt["run_attempt"]
    ):
        raise sr.StrictReceiptError("PROVENANCE_JOB_BINDING_MISMATCH")
    if not isinstance(document["commands"], list):
        raise sr.StrictReceiptError("PROVENANCE_COMMANDS_INVALID")
    commands = {}
    for command in document["commands"]:
        sr._exact_object(command, ("argv", "exit_code"))
        argv = command["argv"]
        if not isinstance(argv, list) or not argv or not all(isinstance(item, str) and item for item in argv):
            raise sr.StrictReceiptError("PROVENANCE_COMMANDS_INVALID")
        key = tuple(argv)
        if key in commands:
            raise sr.StrictReceiptError("PROVENANCE_COMMANDS_INVALID")
        if not isinstance(command["exit_code"], int) or isinstance(command["exit_code"], bool):
            raise sr.StrictReceiptError("PROVENANCE_COMMANDS_INVALID")
        executable = argv[0].rsplit("/", 1)[-1]
        if executable == "rm" or (
            executable == "git"
            and any(item in {"clean", "reset", "checkout", "restore"} for item in argv[1:])
        ):
            return "POST_RUN_CLEANUP_FORBIDDEN", document
        commands[key] = command["exit_code"]
    clean_index = document["clean_check_command_index"]
    if (
        not isinstance(clean_index, int) or isinstance(clean_index, bool)
        or clean_index != len(document["commands"]) - 1
        or tuple(document["commands"][clean_index]["argv"]) != CLEAN_STATUS_COMMAND
    ):
        raise sr.StrictReceiptError("PROVENANCE_CLEAN_CHECK_ORDER_INVALID")
    for required in REQUIRED_COMMANDS:
        if required not in commands:
            raise sr.StrictReceiptError("PROVENANCE_COMMANDS_INVALID")
        if commands[required] != 0:
            return "PROVENANCE_COMMAND_FAILED", document
    if document["run_status"] != "completed" or document["run_conclusion"] != "success":
        return "REMOTE_RUN_NOT_SUCCESS", document
    if document["job_status"] != "completed" or document["job_conclusion"] != "success":
        return "REMOTE_JOB_NOT_SUCCESS", document
    if document["run_event"] != "pull_request":
        return "REMOTE_RUN_EVENT_INVALID", document
    return None, document


def _validate_git_binding(root: Path, receipt: dict, repository: Path) -> None:
    for key, kind in (("start_head_sha", "commit"), ("target_head_sha", "commit")):
        if _git(repository, ["rev-parse", f"{receipt[key]}^{{{kind}}}"]) != receipt[key]:
            raise sr.StrictReceiptError("GIT_HEAD_MISMATCH")
    if _git(repository, ["show", "-s", "--format=%T", receipt["start_head_sha"]]) != receipt["start_head_tree"]:
        raise sr.StrictReceiptError("START_TREE_MISMATCH")
    if _git(repository, ["show", "-s", "--format=%T", receipt["target_head_sha"]]) != receipt["target_head_tree"]:
        raise sr.StrictReceiptError("TARGET_TREE_MISMATCH")
    actual_blob = _git(repository, ["rev-parse", f"{receipt['target_head_sha']}:{receipt['workflow_path']}"])
    if actual_blob != receipt["workflow_blob_oid"]:
        raise sr.StrictReceiptError("WORKFLOW_BLOB_MISMATCH")


def _reproduce_delivery(delivery: Path, receipt: dict, repository: Path) -> None:
    if (delivery / "START_HEAD").read_text(encoding="ascii") != receipt["start_head_sha"] + "\n":
        raise sr.StrictReceiptError("DELIVERY_COORDINATE_MISMATCH")
    if (delivery / "TARGET_HEAD").read_text(encoding="ascii") != receipt["target_head_sha"] + "\n":
        raise sr.StrictReceiptError("DELIVERY_COORDINATE_MISMATCH")
    if (delivery / "TARGET_TREE").read_text(encoding="ascii") != receipt["target_head_tree"] + "\n":
        raise sr.StrictReceiptError("DELIVERY_COORDINATE_MISMATCH")
    runner_temp = Path(os.environ.get("RUNNER_TEMP", tempfile.gettempdir()))
    runner_temp.mkdir(parents=True, exist_ok=True)
    try:
        with tempfile.TemporaryDirectory(prefix="ac25-v42-repro-", dir=runner_temp) as name:
            patch_repo = Path(name) / "patch"
            bundle_repo = Path(name) / "bundle"
            for candidate in (patch_repo, bundle_repo):
                candidate.mkdir()
                code, _ = _run_command(["git", "init", "-q", str(candidate)], cwd=Path(name))
                if code != 0:
                    raise sr.StrictReceiptError("DELIVERY_REPRODUCTION_FAILED")
                code, _ = _run_command(
                    ["git", "-C", str(candidate), "fetch", "-q", "--no-tags", str(repository), receipt["start_head_sha"]],
                    cwd=candidate,
                )
                if code != 0:
                    raise sr.StrictReceiptError("START_HEAD_UNAVAILABLE")
            code, _ = _run_command(
                ["git", "-C", str(patch_repo), "read-tree", receipt["start_head_sha"]], cwd=patch_repo,
            )
            if code != 0:
                raise sr.StrictReceiptError("PATCH_APPLY_FAILED")
            code, _ = _run_command(
                ["git", "-C", str(patch_repo), "apply", "--cached", "--binary", str(delivery / "cumulative.patch")],
                cwd=patch_repo,
            )
            if code != 0:
                raise sr.StrictReceiptError("PATCH_APPLY_FAILED")
            patch_tree = _git(patch_repo, ["write-tree"])
            code, _ = _run_command(
                ["git", "-C", str(bundle_repo), "bundle", "verify", str(delivery / "candidate.bundle")],
                cwd=bundle_repo,
            )
            if code != 0:
                raise sr.StrictReceiptError("BUNDLE_VERIFY_FAILED")
            heads = _git(bundle_repo, ["bundle", "list-heads", str(delivery / "candidate.bundle")])
            if heads != f"{receipt['target_head_sha']} {CANDIDATE_REF}":
                raise sr.StrictReceiptError("BUNDLE_TARGET_HEAD_MISMATCH")
            code, _ = _run_command(
                ["git", "-C", str(bundle_repo), "fetch", "-q", str(delivery / "candidate.bundle"), f"{CANDIDATE_REF}:refs/ac25/candidate"],
                cwd=bundle_repo,
            )
            if code != 0:
                raise sr.StrictReceiptError("BUNDLE_FETCH_FAILED")
            bundle_head = _git(bundle_repo, ["rev-parse", "refs/ac25/candidate"])
            bundle_tree = _git(bundle_repo, ["show", "-s", "--format=%T", "refs/ac25/candidate"])
    except OSError as exc:
        raise sr.StrictReceiptError("DELIVERY_REPRODUCTION_FAILED") from exc
    if bundle_head != receipt["target_head_sha"]:
        raise sr.StrictReceiptError("BUNDLE_TARGET_HEAD_MISMATCH")
    if patch_tree != receipt["target_head_tree"] or bundle_tree != receipt["target_head_tree"] or patch_tree != bundle_tree:
        raise sr.StrictReceiptError("DELIVERY_REPRODUCTION_MISMATCH")


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
                "User-Agent": "butler-ac25-strict-receipt-validator/2",
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=20) as response:
                return json.loads(response.read().decode("utf-8", "strict"))
        except urllib.error.HTTPError as exc:
            if exc.code == 404:
                return {"_http_status": 404}
            raise sr.StrictReceiptError("REMOTE_BINDING_UNKNOWN") from exc
        except (OSError, urllib.error.URLError, json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise sr.StrictReceiptError("REMOTE_BINDING_UNKNOWN") from exc


def _fetch(fetch: Callable[[str], object], url: str):
    try:
        return fetch(url)
    except sr.StrictReceiptError:
        raise
    except Exception as exc:
        raise sr.StrictReceiptError("REMOTE_BINDING_UNKNOWN") from exc


def _pages(fetch: Callable[[str], object], url: str, key: Optional[str] = None) -> list:
    values = []
    for page in range(1, 101):
        separator = "&" if "?" in url else "?"
        payload = _fetch(fetch, f"{url}{separator}per_page=100&page={page}")
        batch = payload.get(key) if key and isinstance(payload, dict) else payload
        if not isinstance(batch, list):
            raise sr.StrictReceiptError("REMOTE_PAGINATION_INVALID")
        values.extend(batch)
        if len(batch) < 100:
            return values
    raise sr.StrictReceiptError("REMOTE_PAGINATION_INCOMPLETE")


def _live_required(api: str, fetch: Callable[[str], object]) -> tuple[tuple[str, int], ...]:
    identities = set()
    protection = _fetch(fetch, f"{api}/branches/{BASE_BRANCH}/protection/required_status_checks")
    if isinstance(protection, dict) and protection.get("_http_status") == 404:
        checks = []
        contexts = []
    else:
        checks = protection.get("checks") if isinstance(protection, dict) else None
        contexts = protection.get("contexts") if isinstance(protection, dict) else None
    if not isinstance(checks, list):
        raise sr.StrictReceiptError("REMOTE_REQUIRED_CHECKS_UNKNOWN")
    if not isinstance(contexts, list) or contexts:
        raise sr.StrictReceiptError("REMOTE_REQUIRED_IDENTITY_UNKNOWN")
    for check in checks:
        name = check.get("context") if isinstance(check, dict) else None
        app_id = check.get("app_id") if isinstance(check, dict) else None
        if not isinstance(name, str) or not isinstance(app_id, int) or app_id <= 0:
            raise sr.StrictReceiptError("REMOTE_REQUIRED_IDENTITY_UNKNOWN")
        identities.add((name, app_id))
    rulesets = _pages(fetch, f"{api}/rulesets?includes_parents=true&target=branch")
    for summary in rulesets:
        if not isinstance(summary, dict) or not isinstance(summary.get("id"), int):
            raise sr.StrictReceiptError("REMOTE_RULESET_INVALID")
        detail = _fetch(fetch, f"{api}/rulesets/{summary['id']}")
        if detail.get("enforcement") != "active" or detail.get("target") != "branch":
            continue
        ref_name = detail.get("conditions", {}).get("ref_name", {})
        includes = ref_name.get("include", [])
        excludes = ref_name.get("exclude", [])
        if not isinstance(includes, list) or not isinstance(excludes, list):
            raise sr.StrictReceiptError("REMOTE_RULESET_INVALID")
        ref = "refs/heads/" + BASE_BRANCH
        def matches(pattern: str) -> bool:
            if pattern == "~DEFAULT_BRANCH":
                return True
            return isinstance(pattern, str) and fnmatch.fnmatchcase(ref, pattern)
        if includes and not any(matches(pattern) for pattern in includes):
            continue
        if any(matches(pattern) for pattern in excludes):
            continue
        for rule in detail.get("rules", []):
            if rule.get("type") != "required_status_checks":
                continue
            for check in rule.get("parameters", {}).get("required_status_checks", []):
                name = check.get("context")
                app_id = check.get("integration_id")
                if not isinstance(name, str) or not isinstance(app_id, int) or app_id <= 0:
                    raise sr.StrictReceiptError("REMOTE_REQUIRED_IDENTITY_UNKNOWN")
                identities.add((name, app_id))
    if not identities:
        raise GateFailure("REQUIRED_CHECK_SET_EMPTY")
    return tuple(sorted(identities, key=lambda item: (item[0].encode("utf-8"), item[1])))


def _live_observed(api: str, target: str, fetch: Callable[[str], object]) -> dict[tuple[str, int], dict]:
    runs = _pages(fetch, f"{api}/commits/{target}/check-runs?filter=latest", "check_runs")
    observed = {}
    for run in runs:
        app = run.get("app") if isinstance(run, dict) else None
        identity = (run.get("name"), app.get("id") if isinstance(app, dict) else None)
        if not isinstance(identity[0], str) or not isinstance(identity[1], int):
            raise sr.StrictReceiptError("REMOTE_OBSERVED_IDENTITY_UNKNOWN")
        if identity in observed:
            raise sr.StrictReceiptError("REMOTE_OBSERVED_ATTEMPT_AMBIGUOUS")
        observed[identity] = run
    return observed


def validate_remote(receipt: dict, provenance: dict, required: dict, observed: dict, fetch: Callable[[str], object]) -> None:
    api = "https://api.github.com/repos/" + receipt["repository"]
    pr = _fetch(fetch, f"{api}/pulls/{receipt['pr_number']}")
    commit = _fetch(fetch, f"{api}/git/commits/{receipt['target_head_sha']}")
    run = _fetch(fetch, f"{api}/actions/runs/{receipt['run_id']}")
    job = _fetch(fetch, f"{api}/actions/jobs/{receipt['exact_head_job_id']}")
    if pr.get("head", {}).get("sha") != receipt["target_head_sha"]:
        raise GateFailure("REMOTE_PR_HEAD_MISMATCH")
    if commit.get("tree", {}).get("sha") != receipt["target_head_tree"]:
        raise GateFailure("REMOTE_HEAD_TREE_MISMATCH")
    if (
        str(run.get("id")) != receipt["run_id"]
        or run.get("head_sha") != receipt["target_head_sha"]
        or str(run.get("run_attempt")) != receipt["run_attempt"]
        or run.get("event") != "pull_request"
        or run.get("workflow_id") != WORKFLOW_ID
        or run.get("path") != WORKFLOW_PATH
    ):
        raise GateFailure("REMOTE_RUN_MISMATCH")
    if run.get("status") != "completed" or run.get("conclusion") != "success":
        raise GateFailure("REMOTE_RUN_NOT_SUCCESS")
    if (
        str(job.get("id")) != receipt["exact_head_job_id"]
        or str(job.get("run_id")) != receipt["run_id"]
        or str(job.get("run_attempt")) != receipt["run_attempt"]
        or job.get("head_sha") != receipt["target_head_sha"]
        or job.get("name") != EXACT_HEAD_JOB_NAME
    ):
        raise GateFailure("REMOTE_JOB_MISMATCH")
    if job.get("status") != "completed" or job.get("conclusion") != "success":
        raise GateFailure("REMOTE_JOB_NOT_SUCCESS")
    live_required = _live_required(api, fetch)
    declared_required = sr.validate_required_checks(required)
    if live_required != declared_required:
        raise GateFailure("REMOTE_REQUIRED_SET_MISMATCH")
    live_observed = _live_observed(api, receipt["target_head_sha"], fetch)
    declared_observed = sr.validate_observed_checks(observed)
    for identity in declared_required:
        actual = live_observed.get(identity)
        declared = declared_observed.get(identity)
        if actual is None or declared is None:
            raise GateFailure("REQUIRED_CHECK_MISSING")
        if actual.get("status") != "completed" or actual.get("conclusion") != "success":
            raise GateFailure("REQUIRED_CHECK_NOT_SUCCESS")
        if declared["status"] != actual.get("status") or declared["conclusion"] != actual.get("conclusion"):
            raise GateFailure("REMOTE_OBSERVED_SET_MISMATCH")
    if provenance["run_conclusion"] != run.get("conclusion") or provenance["job_conclusion"] != job.get("conclusion"):
        raise GateFailure("REMOTE_PROVENANCE_MISMATCH")


def validate_delivery(
    delivery: Path, repository: Path, *, online: bool = False,
    fetch: Optional[Callable[[str], object]] = None,
) -> ValidationResult:
    receipt_valid = False
    evidence_valid = False
    remote = "NOT_RUN"
    try:
        dm.verify_delivery_digests(delivery)
        root = delivery / RECEIPT_DIRNAME
        sr.verify_digest_manifest(root)
        receipt, _ = sr.load_canonical_json(root / "receipt.json")
        _validate_receipt_schema(root, receipt)
        receipt_valid = True
        _validate_git_binding(root, receipt, repository)
        _validate_changed_paths(delivery, root, receipt, repository)
        contract_error = _validate_contract(root, receipt)
        clean_error = _validate_clean(root, receipt, repository)
        checks_error, required, observed = _validate_checks(root, receipt)
        tests_error = _validate_tests(root, receipt)
        provenance_error, provenance = _validate_provenance(root, receipt)
        _reproduce_delivery(delivery, receipt, repository)
        evidence_valid = True
        local_error = next(
            (code for code in (contract_error, clean_error, checks_error, tests_error, provenance_error) if code),
            None,
        )
        if local_error:
            return ValidationResult(True, True, "NOT_RUN" if not online else "FAIL", False, local_error)
        if not online:
            return ValidationResult(True, True, "NOT_RUN", False, "REMOTE_BINDING_NOT_RUN")
        if fetch is None:
            token = os.environ.get("GITHUB_TOKEN", "")
            if not token:
                return ValidationResult(True, True, "UNKNOWN", False, "REMOTE_BINDING_UNKNOWN")
            fetch = GitHubFetcher(token)
        try:
            validate_remote(receipt, provenance, required, observed, fetch)
        except GateFailure as exc:
            return ValidationResult(True, True, "FAIL", False, exc.code)
        remote = "PASS"
        return ValidationResult(True, True, remote, True, "OK")
    except GateFailure as exc:
        return ValidationResult(receipt_valid, evidence_valid, "FAIL" if online else remote, False, exc.code)
    except (sr.StrictReceiptError, FileNotFoundError, OSError) as exc:
        code = exc.code if isinstance(exc, sr.StrictReceiptError) else "RECEIPT_FILE_NOT_FOUND"
        return ValidationResult(receipt_valid, False, "UNKNOWN" if online else remote, False, code)


def validate_bundle(root: Path, repository: Path, **kwargs) -> ValidationResult:
    """Compatibility name; v4.2 requires a delivery root, not a receipt root."""
    return validate_delivery(root, repository, **kwargs)


def _emit(result: ValidationResult) -> None:
    sys.stdout.write(
        f"RECEIPT_VALID={int(result.receipt_valid)}\n"
        f"EVIDENCE_VALID={int(result.evidence_valid)}\n"
        f"REMOTE_BINDING={result.remote_binding}\n"
        f"AC25_PASS={int(result.ac25_pass)}\n"
        f"ERROR_CODE={result.error_code}\n"
    )


def _process_exit(command: str, result: ValidationResult) -> int:
    if command == "diagnose":
        return 0 if result.receipt_valid and result.evidence_valid else 1
    return 0 if result.ac25_pass else 1


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("command", choices=("diagnose", "gate"))
    parser.add_argument("--delivery-root", required=True)
    parser.add_argument("--repository", required=True)
    parser.add_argument("--online", action="store_true")
    try:
        args = parser.parse_args(argv)
        result = validate_delivery(
            Path(args.delivery_root), Path(args.repository), online=args.online,
        )
    except BaseException:
        result = ValidationResult(False, False, "UNKNOWN", False, "VALIDATOR_INTERNAL_ERROR")
        args = argparse.Namespace(command="gate")
    _emit(result)
    return _process_exit(args.command, result)


if __name__ == "__main__":
    raise SystemExit(main())
