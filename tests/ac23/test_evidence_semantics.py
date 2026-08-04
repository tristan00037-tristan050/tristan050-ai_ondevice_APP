from __future__ import annotations

import copy
import hashlib
import io
import json
import os
import shutil
import subprocess
import sys
import tarfile
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

from tests.ac23.test_junit_closed_profile import JUNIT_CASES


TOOLS_ROOT = Path(__file__).parents[2] / "tools" / "ac23"
sys.path.insert(0, os.fspath(TOOLS_ROOT))
from junit_closed_profile import parse_pytest_junit_closed  # noqa: E402
from verify_candidate_artifact_identity import (  # noqa: E402
    VerificationError,
    load_evidence_policy,
    verify_mutation_results,
)


CASES = [
    ("command_nonzero", "E_EVIDENCE_NONZERO_EXIT"),
    ("stdout_missing", "E_EVIDENCE_RAW_MISSING"),
    ("stderr_missing", "E_EVIDENCE_RAW_MISSING"),
    ("stdout_digest", "E_EVIDENCE_RAW_DIGEST"),
    ("stderr_digest", "E_EVIDENCE_RAW_DIGEST"),
    ("command_missing", "E_EVIDENCE_COMMAND"),
    ("command_extra", "E_EVIDENCE_COMMAND"),
    ("argv_swap", "E_EVIDENCE_COMMAND"),
    ("cwd_swap", "E_EVIDENCE_COMMAND"),
    ("sequence_gap", "E_EVIDENCE_COMMAND"),
    ("timestamp_syntax", "E_EVIDENCE_TIMESTAMP"),
    ("timestamp_order", "E_EVIDENCE_TIMESTAMP"),
    ("mutation_details_missing", "E_EVIDENCE_INVENTORY"),
    ("mutation_junit_missing", "E_EVIDENCE_INVENTORY"),
    ("mutation_stream_missing", "E_EVIDENCE_INVENTORY"),
    ("provisional_key", "E_EVIDENCE_SCHEMA"),
    ("junit_failure", "E_EVIDENCE_JUNIT_STATUS"),
    ("junit_error", "E_EVIDENCE_JUNIT_STATUS"),
    ("junit_skipped", "E_EVIDENCE_JUNIT_STATUS"),
    ("testcase_missing", "E_EVIDENCE_TESTCASE_SET"),
    ("testcase_duplicate", "E_EVIDENCE_JUNIT_IDENTITY"),
    ("category_swap", "E_EVIDENCE_MUTATION_MAPPING"),
    ("details_junit_digest", "E_EVIDENCE_RAW_DIGEST"),
    ("summary_false", "E_EVIDENCE_SUMMARY"),
    ("frozen_id_missing", "E_EVIDENCE_POLICY_VERSION"),
    ("frozen_id_duplicate", "E_EVIDENCE_INVENTORY"),
    ("frozen_run_swap", "E_EVIDENCE_INVENTORY"),
    ("regression_testcase_missing", "E_EVIDENCE_TESTCASE_SET"),
    ("checksum_stale", "E_PACKAGE_CHECKSUM_DIGEST"),
    ("checksum_missing", "E_PACKAGE_INVENTORY"),
    ("checksum_duplicate", "E_PACKAGE_CHECKSUM_FORMAT"),
    ("checksum_extra", "E_PACKAGE_INVENTORY"),
    ("checksum_unsorted", "E_PACKAGE_CHECKSUM_FORMAT"),
    ("checksum_self", "E_PACKAGE_CHECKSUM_FORMAT"),
    ("policy_mismatch", "E_EVIDENCE_POLICY"),
    ("object_format_sha256", "E_OBJECT_FORMAT_UNSUPPORTED"),
]

EXTERNAL_RESULT_CASES = {
    "mutation_details_missing",
    "mutation_junit_missing",
    "mutation_stream_missing",
    "provisional_key",
    "junit_failure",
    "junit_error",
    "junit_skipped",
    "testcase_missing",
    "testcase_duplicate",
    "category_swap",
    "details_junit_digest",
    "summary_false",
}


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _replace(path: Path, payload: bytes) -> None:
    replacement = path.with_name(path.name + ".replacement")
    replacement.write_bytes(payload)
    os.replace(replacement, path)


def _canonical(value: object) -> bytes:
    return (json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True) + "\n").encode()


def _reseal(package: Path) -> None:
    checksum = package / "SHA256SUMS.txt"
    files = sorted(path for path in package.rglob("*") if path.is_file() and path != checksum)
    _replace(checksum, "".join(f"{_sha(path)}  {path.relative_to(package).as_posix()}\n" for path in files).encode())


def _load_evidence(path: Path) -> dict[str, bytes]:
    with tarfile.open(path, "r:") as archive:
        return {
            member.name.rstrip("/"): archive.extractfile(member).read()
            for member in archive.getmembers()
            if member.isfile()
        }


def _write_evidence(path: Path, payloads: dict[str, bytes]) -> None:
    replacement = path.with_name(path.name + ".replacement")
    with tarfile.open(replacement, "w", format=tarfile.PAX_FORMAT) as archive:
        for name, payload in sorted(payloads.items()):
            member = tarfile.TarInfo(name)
            member.mode = 0o644
            member.uid = member.gid = member.mtime = 0
            member.uname = member.gname = ""
            member.size = len(payload)
            archive.addfile(member, io.BytesIO(payload))
    os.replace(replacement, path)


def _commands(payloads: dict[str, bytes]) -> list[dict[str, object]]:
    return [json.loads(line) for line in payloads["commands.jsonl"].decode().splitlines()]


def _store_commands(payloads: dict[str, bytes], commands: list[dict[str, object]]) -> None:
    payloads["commands.jsonl"] = "".join(json.dumps(item, separators=(",", ":"), sort_keys=True) + "\n" for item in commands).encode()


def _recount_junit(root: ET.Element) -> None:
    suites = [root] if root.tag == "testsuite" else list(root)
    for suite in suites:
        cases = [child for child in suite if child.tag == "testcase"]
        counts = {
            "tests": len(cases),
            "failures": sum(any(child.tag == "failure" for child in case) for case in cases),
            "errors": sum(any(child.tag == "error" for child in case) for case in cases),
            "skipped": sum(any(child.tag == "skipped" for child in case) for case in cases),
        }
        for key, value in counts.items():
            suite.set(key, str(value))


def _mutate_junit(payloads: dict[str, bytes], case: str) -> None:
    path = "mutation/pytest_mutation.xml"
    root = ET.fromstring(payloads[path])
    testcases = root.findall(".//testcase")
    if case in {"junit_failure", "junit_error", "junit_skipped"}:
        ET.SubElement(testcases[0], case.removeprefix("junit_"))
    elif case == "testcase_missing":
        parent = next(suite for suite in ([root] if root.tag == "testsuite" else list(root)) if testcases[0] in list(suite))
        parent.remove(testcases[0])
    else:
        parent = next(suite for suite in ([root] if root.tag == "testsuite" else list(root)) if testcases[0] in list(suite))
        parent.append(copy.deepcopy(testcases[0]))
    _recount_junit(root)
    payloads[path] = ET.tostring(root, encoding="utf-8", xml_declaration=True)
    details = json.loads(payloads["mutation/mutation_results_v3.json"])
    details["junit_sha256"] = hashlib.sha256(payloads[path]).hexdigest()
    payloads["mutation/mutation_results_v3.json"] = _canonical(details)


def _mutate_evidence(payloads: dict[str, bytes], case: str) -> None:
    if case.startswith("command_") or case in {"argv_swap", "cwd_swap", "sequence_gap", "timestamp_syntax", "timestamp_order", "stdout_digest", "stderr_digest"}:
        commands = _commands(payloads)
        if case == "command_nonzero": commands[0]["exit_code"] = 97
        elif case == "command_missing": commands.pop()
        elif case == "command_extra": commands.append(copy.deepcopy(commands[-1]))
        elif case == "argv_swap": commands[0]["argv"] = ["false"]
        elif case == "cwd_swap": commands[0]["cwd"] = "candidate/elsewhere"
        elif case == "sequence_gap": commands[0]["sequence"] = 2
        elif case == "timestamp_syntax": commands[0]["start_utc"] = "not-time"
        elif case == "timestamp_order": commands[0]["start_utc"], commands[0]["end_utc"] = commands[0]["end_utc"], commands[0]["start_utc"]
        elif case == "stdout_digest": commands[0]["stdout_sha256"] = "0" * 64
        elif case == "stderr_digest": commands[0]["stderr_sha256"] = "0" * 64
        _store_commands(payloads, commands)
    elif case == "stdout_missing": payloads.pop("stdout/0001.bin")
    elif case == "stderr_missing": payloads.pop("stderr/0001.bin")
    elif case == "mutation_details_missing": payloads.pop("mutation/mutation_results_v3.json")
    elif case == "mutation_junit_missing": payloads.pop("mutation/pytest_mutation.xml")
    elif case == "mutation_stream_missing": payloads.pop("mutation/pytest_mutation.stdout.bin")
    elif case == "provisional_key":
        value = json.loads(payloads["mutation/mutation_results_v3.json"]); value["provisional"] = True
        payloads["mutation/mutation_results_v3.json"] = _canonical(value)
    elif case in {"junit_failure", "junit_error", "junit_skipped", "testcase_missing", "testcase_duplicate"}: _mutate_junit(payloads, case)
    elif case in {"category_swap", "details_junit_digest", "summary_false"}:
        value = json.loads(payloads["mutation/mutation_results_v3.json"])
        if case == "category_swap": value["legacy_categories"][0]["category"] = 2
        elif case == "details_junit_digest": value["junit_sha256"] = "0" * 64
        else: value["summary"]["failed"] = 1
        payloads["mutation/mutation_results_v3.json"] = _canonical(value)
    elif case == "frozen_id_duplicate":
        payloads["regression/" + "frozen_" + "19_details.json"] = b"{}\n"
    elif case == "frozen_run_swap":
        payloads["regression/" + "frozen_" + "19_summary.json"] = b"{}\n"
    elif case == "regression_testcase_missing":
        root = ET.fromstring(payloads["junit/0002.xml"])
        suite = next(root.iter("testsuite"))
        testcase = next(root.iter("testcase"))
        suite.remove(testcase)
        _recount_junit(root)
        payloads["junit/0002.xml"] = ET.tostring(
            root, encoding="utf-8", xml_declaration=True
        )


def _run_verifier(package: Path) -> tuple[int, str, str]:
    completed = subprocess.run([sys.executable, os.fspath(package / "VERIFY/verify_candidate_artifact_identity.py"), os.fspath(package)], cwd=package, env={"PATH": os.environ.get("PATH", ""), "LC_ALL": "C", "TZ": "UTC"}, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=False)
    code = ""
    for line in completed.stderr.splitlines():
        try: code = json.loads(line).get("error_code", code)
        except json.JSONDecodeError: pass
    return completed.returncode, code, completed.stdout


def _valid_external_mutation_payloads() -> tuple[dict[str, bytes], dict[str, object]]:
    policy = load_evidence_policy(
        (TOOLS_ROOT / "evidence_policy_v3.json").read_bytes()
    )
    expected = sorted(
        {
            testcase
            for item in policy["legacy_mutation_categories"]
            for testcase in item["testcases"]
        }
        | {item["testcase"] for item in policy["evidence_semantic_categories"]}
        | {
            item["testcase"]
            for item in policy["junit_profile"]["closed_junit_cases"]
        }
    )
    root = ET.Element("testsuites", {"name": "pytest tests"})
    suite = ET.SubElement(
        root,
        "testsuite",
        {
            "name": "pytest",
            "errors": "0",
            "failures": "0",
            "skipped": "0",
            "tests": str(len(expected)),
            "time": "0",
            "timestamp": "2026-08-04T00:00:00.000000+00:00",
            "hostname": "unit-fixture",
        },
    )
    for identity in expected:
        classname, name = identity.split("::", 1)
        ET.SubElement(
            suite,
            "testcase",
            {"classname": classname, "name": name, "time": "0"},
        )
    junit = ET.tostring(root, encoding="utf-8", xml_declaration=True)
    limits = policy["limits"]
    canonical = parse_pytest_junit_closed(
        junit,
        expected_testcase_ids=frozenset(expected),
        max_bytes=limits["max_junit_bytes"],
        max_elements=limits["max_xml_elements"],
    ).to_bytes()
    stdout = b""
    stderr = b""
    legacy = policy["legacy_mutation_categories"]
    semantic = policy["evidence_semantic_categories"]
    closed = policy["junit_profile"]["closed_junit_cases"]
    details = {
        "schema_version": "butler.box5.ac23-mutation-results.v3",
        "argv": [
            "python3", "-m", "pytest", "-q", "--disable-warnings",
            "tests/ac23/test_candidate_artifact_identity.py",
            "tests/ac23/test_evidence_semantics.py",
            "-k", "mutation or evidence_semantics_attack or closed_junit_integration_attack",
            "--junitxml=.ac23-mutation-run/results.xml",
            "--basetemp", ".ac23-mutation-run/tmp",
        ],
        "cwd": "candidate",
        "start_utc": "2026-08-04T00:00:00.000Z",
        "end_utc": "2026-08-04T00:00:01.000Z",
        "exit_code": 0,
        "termination": "exit",
        "subject_checksum_sha256": "1" * 64,
        "subject_identity_sha256": "2" * 64,
        "subject_head_commit": "3" * 40,
        "subject_head_tree": "4" * 40,
        "legacy_categories": [{**item, "status": "PASS"} for item in legacy],
        "evidence_semantic_categories": [{**item, "status": "PASS"} for item in semantic],
        "closed_junit_cases": [{**item, "status": "PASS"} for item in closed],
        "stdout_path": "mutation/pytest_mutation.stdout.bin",
        "stdout_sha256": hashlib.sha256(stdout).hexdigest(),
        "stderr_path": "mutation/pytest_mutation.stderr.bin",
        "stderr_sha256": hashlib.sha256(stderr).hexdigest(),
        "junit_path": "mutation/pytest_mutation.xml",
        "junit_sha256": hashlib.sha256(junit).hexdigest(),
        "canonical_path": "mutation/canonical.json",
        "canonical_sha256": hashlib.sha256(canonical).hexdigest(),
        "summary": {
            "failed": 0,
            "legacy_categories_passed": len(legacy),
            "legacy_subcases_passed": sum(len(item["testcases"]) for item in legacy),
            "existing_semantic_categories_passed": len(semantic),
            "closed_junit_categories_passed": len({item["category"] for item in closed}),
            "closed_junit_subcases_passed": len(closed),
        },
    }
    payloads = {
        "mutation/mutation_results_v3.json": _canonical(details),
        "mutation/pytest_mutation.stdout.bin": stdout,
        "mutation/pytest_mutation.stderr.bin": stderr,
        "mutation/pytest_mutation.xml": junit,
        "mutation/canonical.json": canonical,
    }
    return payloads, policy


def _assert_external_mutation_failure(case: str, expected: str) -> None:
    payloads, policy = _valid_external_mutation_payloads()
    details_path = "mutation/mutation_results_v3.json"
    junit_path = "mutation/pytest_mutation.xml"
    if case == "mutation_details_missing":
        payloads.pop(details_path)
    elif case == "mutation_junit_missing":
        payloads.pop(junit_path)
    elif case == "mutation_stream_missing":
        payloads.pop("mutation/pytest_mutation.stdout.bin")
    elif case == "provisional_key":
        details = json.loads(payloads[details_path])
        details["provisional"] = True
        payloads[details_path] = _canonical(details)
    elif case in {"junit_failure", "junit_error", "junit_skipped", "testcase_missing", "testcase_duplicate"}:
        root = ET.fromstring(payloads[junit_path])
        suite = next(root.iter("testsuite"))
        testcases = list(root.iter("testcase"))
        if case.startswith("junit_"):
            ET.SubElement(testcases[0], case.removeprefix("junit_"))
        elif case == "testcase_missing":
            suite.remove(testcases[0])
            suite.set("tests", str(len(testcases) - 1))
        else:
            suite.append(copy.deepcopy(testcases[0]))
            suite.set("tests", str(len(testcases) + 1))
        payloads[junit_path] = ET.tostring(root, encoding="utf-8", xml_declaration=True)
        details = json.loads(payloads[details_path])
        details["junit_sha256"] = hashlib.sha256(payloads[junit_path]).hexdigest()
        payloads[details_path] = _canonical(details)
    else:
        details = json.loads(payloads[details_path])
        if case == "category_swap":
            details["legacy_categories"][0]["category"] = 2
        elif case == "details_junit_digest":
            details["junit_sha256"] = "0" * 64
        else:
            details["summary"]["failed"] = 1
        payloads[details_path] = _canonical(details)
    with pytest.raises(VerificationError) as captured:
        verify_mutation_results(payloads, policy)
    assert captured.value.code == expected


def _assert_checksum_valid(package: Path) -> None:
    completed = subprocess.run(
        ["shasum", "-a", "256", "-c", "SHA256SUMS.txt"],
        cwd=package,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    assert completed.returncode == 0


@pytest.mark.parametrize(("case", "expected"), CASES, ids=[case for case, _ in CASES])
def test_evidence_semantics_attack(tmp_path: Path, case: str, expected: str) -> None:
    source_text = os.environ.get("AC23_PACKAGE_ROOT")
    if not source_text:
        pytest.skip("AC23_PACKAGE_ROOT is required")
    if case in EXTERNAL_RESULT_CASES:
        _assert_external_mutation_failure(case, expected)
        return
    package = tmp_path / "package"
    source_evidence_digest = _sha(Path(source_text) / "EVIDENCE/evidence_raw.tar")
    shutil.copytree(Path(source_text), package, copy_function=shutil.copy2)
    evidence_path = package / "EVIDENCE/evidence_raw.tar"

    if case.startswith("checksum_"):
        checksum = package / "SHA256SUMS.txt"
        lines = checksum.read_bytes().splitlines(keepends=True)
        if case == "checksum_stale": _replace(package / "README_KO.md", (package / "README_KO.md").read_bytes() + b"x")
        elif case == "checksum_missing": _replace(checksum, b"".join(lines[:-1]))
        elif case == "checksum_duplicate": _replace(checksum, b"".join(lines + [lines[0]]))
        elif case == "checksum_extra": _replace(checksum, b"".join(lines + [b"0" * 64 + b"  zzzz-extra\n"]))
        elif case == "checksum_unsorted": _replace(checksum, b"".join(reversed(lines)))
        else: _replace(checksum, b"".join(lines + [b"0" * 64 + b"  SHA256SUMS.txt\n"]))
    elif case in {"policy_mismatch", "frozen_id_missing"}:
        policy = package / "VERIFY/evidence_policy_v3.json"
        if case == "frozen_id_missing":
            value = json.loads(policy.read_text(encoding="utf-8"))
            value["frozen_" + "acceptance"] = []
            _replace(policy, _canonical(value))
        else:
            _replace(policy, policy.read_bytes().rstrip() + b" \n")
        _reseal(package)
    elif case == "object_format_sha256":
        manifest_path = package / "IDENTITY/candidate_artifact_identity.json"
        manifest = json.loads(manifest_path.read_text()); manifest["object_format"] = "sha256"
        _replace(manifest_path, _canonical(manifest)); _reseal(package)
    else:
        payloads = _load_evidence(evidence_path)
        _mutate_evidence(payloads, case)
        _write_evidence(evidence_path, payloads)
        manifest_path = package / "IDENTITY/candidate_artifact_identity.json"
        manifest = json.loads(manifest_path.read_text()); manifest["evidence_sha256"] = _sha(evidence_path)
        _replace(manifest_path, _canonical(manifest)); _reseal(package)

    if not case.startswith("checksum_"):
        _assert_checksum_valid(package)
    exit_code, error_code, stdout = _run_verifier(package)
    assert exit_code != 0
    assert error_code == expected
    assert "AC23_PASS=YES" not in stdout
    assert _sha(Path(source_text) / "EVIDENCE/evidence_raw.tar") == source_evidence_digest


@pytest.mark.parametrize(
    ("case", "category", "fixture_payload", "expected"),
    JUNIT_CASES,
    ids=[case for case, _, _, _ in JUNIT_CASES],
)
def test_closed_junit_integration_attack(
    tmp_path: Path,
    case: str,
    category: int,
    fixture_payload: bytes,
    expected: str,
) -> None:
    del category
    source_text = os.environ.get("AC23_PACKAGE_ROOT")
    if not source_text:
        pytest.skip("AC23_PACKAGE_ROOT is required")
    source = Path(source_text)
    source_digest = _sha(source / "EVIDENCE/evidence_raw.tar")
    package = tmp_path / "package"
    shutil.copytree(source, package, copy_function=shutil.copy2)
    evidence_path = package / "EVIDENCE/evidence_raw.tar"
    payloads = _load_evidence(evidence_path)
    junit_path = "junit/0001.xml"
    payloads[junit_path] = (
        b"x" * (16_777_216 + 1) if case == "size_limit" else fixture_payload
    )
    _write_evidence(evidence_path, payloads)
    manifest_path = package / "IDENTITY/candidate_artifact_identity.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["evidence_sha256"] = _sha(evidence_path)
    _replace(manifest_path, _canonical(manifest))
    _reseal(package)

    _assert_checksum_valid(package)
    exit_code, error_code, stdout = _run_verifier(package)
    assert exit_code != 0
    assert error_code == expected
    assert "AC23_PASS=YES" not in stdout
    assert _sha(source / "EVIDENCE/evidence_raw.tar") == source_digest
