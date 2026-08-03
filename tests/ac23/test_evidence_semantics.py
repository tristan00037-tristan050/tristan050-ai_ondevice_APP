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
    ("junit_failure", "E_EVIDENCE_JUNIT"),
    ("junit_error", "E_EVIDENCE_JUNIT"),
    ("junit_skipped", "E_EVIDENCE_JUNIT"),
    ("testcase_missing", "E_EVIDENCE_TESTCASE_SET"),
    ("testcase_duplicate", "E_EVIDENCE_TESTCASE_SET"),
    ("category_swap", "E_EVIDENCE_MUTATION_MAPPING"),
    ("details_junit_digest", "E_EVIDENCE_RAW_DIGEST"),
    ("summary_false", "E_EVIDENCE_SUMMARY"),
    ("frozen_id_missing", "E_EVIDENCE_FROZEN_MAPPING"),
    ("frozen_id_duplicate", "E_EVIDENCE_FROZEN_MAPPING"),
    ("frozen_run_swap", "E_EVIDENCE_FROZEN_MAPPING"),
    ("frozen_raw_missing", "E_EVIDENCE_FROZEN_MAPPING"),
    ("checksum_stale", "E_PACKAGE_CHECKSUM_DIGEST"),
    ("checksum_missing", "E_PACKAGE_INVENTORY"),
    ("checksum_duplicate", "E_PACKAGE_CHECKSUM_FORMAT"),
    ("checksum_extra", "E_PACKAGE_INVENTORY"),
    ("checksum_unsorted", "E_PACKAGE_CHECKSUM_FORMAT"),
    ("checksum_self", "E_PACKAGE_CHECKSUM_FORMAT"),
    ("policy_mismatch", "E_EVIDENCE_POLICY"),
    ("object_format_sha256", "E_OBJECT_FORMAT_UNSUPPORTED"),
]


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
    totals = {"tests": 0, "failures": 0, "errors": 0, "skipped": 0}
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
            totals[key] += value
    if root.tag == "testsuites":
        for key, value in totals.items():
            root.set(key, str(value))


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
    details = json.loads(payloads["mutation/mutation_results_v2.json"])
    details["junit_sha256"] = hashlib.sha256(payloads[path]).hexdigest()
    payloads["mutation/mutation_results_v2.json"] = _canonical(details)


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
    elif case == "mutation_details_missing": payloads.pop("mutation/mutation_results_v2.json")
    elif case == "mutation_junit_missing": payloads.pop("mutation/pytest_mutation.xml")
    elif case == "mutation_stream_missing": payloads.pop("mutation/pytest_mutation.stdout.bin")
    elif case == "provisional_key":
        value = json.loads(payloads["mutation/mutation_results_v2.json"]); value["provisional"] = True
        payloads["mutation/mutation_results_v2.json"] = _canonical(value)
    elif case in {"junit_failure", "junit_error", "junit_skipped", "testcase_missing", "testcase_duplicate"}: _mutate_junit(payloads, case)
    elif case in {"category_swap", "details_junit_digest", "summary_false"}:
        value = json.loads(payloads["mutation/mutation_results_v2.json"])
        if case == "category_swap": value["legacy_categories"][0]["category"] = 2
        elif case == "details_junit_digest": value["junit_sha256"] = "0" * 64
        else: value["summary"]["failed"] = 1
        payloads["mutation/mutation_results_v2.json"] = _canonical(value)
    elif case.startswith("frozen_"):
        value = json.loads(payloads["regression/frozen_19_details.json"])
        if case == "frozen_id_missing": value.pop()
        elif case == "frozen_id_duplicate": value[-1] = copy.deepcopy(value[0])
        elif case == "frozen_run_swap": value[0]["run_ids"] = ["integration-lock"]
        else: value[0]["observed_results"] = []
        payloads["regression/frozen_19_details.json"] = _canonical(value)


def _run_verifier(package: Path) -> tuple[int, str, str]:
    completed = subprocess.run([sys.executable, os.fspath(package / "VERIFY/verify_candidate_artifact_identity.py"), os.fspath(package)], cwd=package, env={"PATH": os.environ.get("PATH", ""), "LC_ALL": "C", "TZ": "UTC"}, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=False)
    code = ""
    for line in completed.stderr.splitlines():
        try: code = json.loads(line).get("error_code", code)
        except json.JSONDecodeError: pass
    return completed.returncode, code, completed.stdout


@pytest.mark.parametrize(("case", "expected"), CASES, ids=[case for case, _ in CASES])
def test_evidence_semantics_attack(tmp_path: Path, case: str, expected: str) -> None:
    source_text = os.environ.get("AC23_PACKAGE_ROOT")
    if not source_text:
        pytest.skip("AC23_PACKAGE_ROOT is required")
    package = tmp_path / "package"
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
    elif case == "policy_mismatch":
        policy = package / "VERIFY/evidence_policy_v2.json"
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

    exit_code, error_code, stdout = _run_verifier(package)
    assert exit_code != 0
    assert error_code == expected
    assert "AC23_PASS=YES" not in stdout
