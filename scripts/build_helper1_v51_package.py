#!/usr/bin/env python3
"""Build one deterministic Helper1 protected-verifier closure handoff."""
from __future__ import annotations

import argparse
import gzip
import hashlib
import io
import json
import os
import re
import shutil
import stat
import subprocess
import tarfile
import tempfile
import zipfile
import unicodedata
import xml.etree.ElementTree as ET
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parents[1]
PACKAGE_ROOT = "Butler_Helper1_v2_A4_ProducerEvidenceBindingClosure_20260804_codex"
START_TREE = "243074f44cf6883a5ad9665a2c40132c7c42a535"
BASE_COMMIT = "390af710bdc76a58be3158b6bcbf0638d62b49a4"
BASE_BUNDLE_SHA256 = "53fccfead8b2089dc3b595ed4ce7f01e9d3e9664ec67faca045fa7dfdb4ed41d"
V4_INPUT_SHA256 = "3d73b50e6a2b6fed6edeb686b8e591f858e280af0d580031b7c9cb171fe57b50"
ZIP_TIME = (1980, 1, 1, 0, 0, 0)
SUM_RE = re.compile(r"^([0-9a-f]{64})  ([^\x00\r\n]+)$")
CANONICAL_VECTOR_PATHS = (
    "tests/helper1_v2/vectors/canonical_json_v1.json",
    "tests/helper1_v2/vectors/ed25519_rfc8032_subset.json",
)
APPROVAL_POLICY_PATH = "contracts/helper1/retrieval-approval-trust-policy-v1.json"
CHAIN_POLICY_PATH = ROOT / "contracts/helper1/trusted-verifier-policy-v1.json"
CHAIN_ID = "helper1-v51-a4-closure"
CHAIN_GENERATION = 15
PREDECESSOR_GENERATION = 14
ROLLBACK_GENERATION = 13
EXPECTED_PREDECESSOR = {
    "generation": 14,
    "package_sha256": "41870dec77c3f503f34fa5742f13ea242cf9cc6941f4f2ee1b072276fb34a114",
    "result_tree": "482d98334b80b7000e31ff8cacd508cd166f54c8",
}
EXPECTED_ROLLBACK = {
    "generation": 13,
    "package_sha256": "76e7cffe09e90e7ad5b9b632c5eb6793a5abd9ec6cf9d8eed28f206182f085cc",
    "result_tree": "32c025dff173cf4526174a7df4ccc899345e47dc",
}


class PackageBuildError(RuntimeError):
    pass


def _run(argv: tuple[str, ...], *, cwd: Path, env: dict[str, str] | None = None) -> bytes:
    completed = subprocess.run(
        argv,
        cwd=cwd,
        env=env,
        shell=False,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=120,
        check=False,
    )
    if completed.returncode != 0:
        raise PackageBuildError("PACKAGE_GIT_OPERATION_FAILED")
    return completed.stdout


def _safe_path(value: str) -> str:
    path = PurePosixPath(value)
    if (
        not value
        or value != unicodedata.normalize("NFC", value)
        or value.startswith("/")
        or "\\" in value
        or any(part in {"", ".", ".."} for part in path.parts)
    ):
        raise PackageBuildError("PACKAGE_PATH_INVALID")
    return path.as_posix()


def _changed_paths() -> tuple[str, ...]:
    raw = _run(
        ("git", "ls-files", "-m", "-o", "-d", "--exclude-standard", "-z"),
        cwd=ROOT,
    )
    paths = tuple(sorted({_safe_path(item.decode("utf-8")) for item in raw.split(b"\0") if item}))
    if not paths:
        raise PackageBuildError("PACKAGE_CHANGESET_EMPTY")
    if len({name.casefold() for name in paths}) != len(paths):
        raise PackageBuildError("PACKAGE_PATH_COLLISION")
    for name in paths:
        path = ROOT / name
        if not path.exists() or path.is_symlink() or not path.is_file():
            raise PackageBuildError("PACKAGE_CHANGESET_UNSUPPORTED")
    return paths


def _result_material(paths: tuple[str, ...], temporary: Path) -> tuple[str, bytes]:
    index = temporary / "index"
    object_directory = temporary / "objects"
    object_directory.mkdir(mode=0o700)
    environment = dict(os.environ)
    environment["GIT_INDEX_FILE"] = str(index)
    environment["GIT_OBJECT_DIRECTORY"] = str(object_directory)
    environment["GIT_ALTERNATE_OBJECT_DIRECTORIES"] = str(ROOT / ".git" / "objects")
    _run(("git", "read-tree", "HEAD"), cwd=ROOT, env=environment)
    _run(("git", "add", "-A", "--", *paths), cwd=ROOT, env=environment)
    tree = _run(("git", "write-tree"), cwd=ROOT, env=environment).decode("ascii").strip()
    patch = _run(
        ("git", "diff", "--cached", "--binary", "--full-index", "HEAD", "--", *paths),
        cwd=ROOT,
        env=environment,
    )
    if not patch:
        raise PackageBuildError("PACKAGE_PATCH_EMPTY")
    changed = tuple(
        item.decode("utf-8")
        for item in _run(
            ("git", "diff", "--cached", "--name-only", "-z", "HEAD"),
            cwd=ROOT,
            env=environment,
        ).split(b"\0")
        if item
    )
    if changed != paths:
        raise PackageBuildError("PACKAGE_CHANGESET_IDENTITY_MISMATCH")
    return tree, patch


def _base_to_start_patch() -> bytes:
    patch = _run(
        ("git", "diff", "--binary", "--full-index", BASE_COMMIT, "HEAD"),
        cwd=ROOT,
    )
    if not patch:
        raise PackageBuildError("PACKAGE_BASE_PATCH_EMPTY")
    return patch


def _overlay(paths: tuple[str, ...]) -> bytes:
    tar_buffer = io.BytesIO()
    with tarfile.open(fileobj=tar_buffer, mode="w", format=tarfile.GNU_FORMAT) as archive:
        for name in paths:
            path = ROOT / name
            data = path.read_bytes()
            info = tarfile.TarInfo(name)
            info.size = len(data)
            info.mode = 0o755 if stat.S_IMODE(path.stat().st_mode) & 0o111 else 0o644
            info.uid = info.gid = 0
            info.uname = info.gname = ""
            info.mtime = 0
            archive.addfile(info, io.BytesIO(data))
    output = io.BytesIO()
    with gzip.GzipFile(filename="", mode="wb", fileobj=output, mtime=0, compresslevel=9) as gz:
        gz.write(tar_buffer.getvalue())
    return output.getvalue()


def _write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    path.write_bytes(data)


def _load_chain_contract() -> dict[str, object]:
    try:
        if (
            CHAIN_POLICY_PATH.is_symlink()
            or not CHAIN_POLICY_PATH.is_file()
        ):
            raise PackageBuildError("PACKAGE_CHAIN_CONTRACT_UNAVAILABLE")
        policy = json.loads(CHAIN_POLICY_PATH.read_bytes())
        contract = policy["handoff_chain_authority"]
        producer = policy["producer_package_contract"]
    except (KeyError, OSError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise PackageBuildError("PACKAGE_CHAIN_CONTRACT_INVALID") from exc
    if (
        type(policy) is not dict
        or policy.get("enabled") is not False
        or type(contract) is not dict
        or set(contract) != {
            "schema_version",
            "chain_id",
            "authority_mode",
            "approved_public_key_b64",
            "approved_public_key_sha256",
            "required_environment",
            "required_check_name",
        }
        or contract.get("schema_version") != "butler.helper1.handoff-chain-authority.v1"
        or contract.get("chain_id") != CHAIN_ID
        or contract.get("authority_mode") != "PROTECTED_WORKFLOW_SIGNED_CHAIN"
        or contract.get("approved_public_key_b64") is not None
        or contract.get("approved_public_key_sha256") is not None
        or contract.get("required_environment") != "helper1-production-verifier"
        or contract.get("required_check_name") != "helper1-v2/protected-verdict"
        or type(producer) is not dict
        or producer.get("schema_version") != "butler.helper1.producer-package-contract.v1"
        or producer.get("chain_id") != CHAIN_ID
        or producer.get("candidate_generation") != CHAIN_GENERATION
        or producer.get("package_relative_path") != "package/helper1-v51.zip"
        or producer.get("descriptor_relative_path") != "package/helper1-v51.candidate.json"
        or producer.get("immediate_predecessor") != EXPECTED_PREDECESSOR
        or producer.get("rollback_record") != EXPECTED_ROLLBACK
    ):
        raise PackageBuildError("PACKAGE_CHAIN_CONTRACT_INVALID")
    return policy


def _candidate_package_material(
    package_path: Path,
    *,
    generation: int,
    require_result_patch: bool,
) -> tuple[dict[str, object], bytes, bytes | None, bytes | None, bytes | None]:
    if not package_path.is_file() or package_path.is_symlink():
        raise PackageBuildError("PACKAGE_PREVIOUS_RESULT_MISSING")
    package = package_path.read_bytes()
    try:
        with zipfile.ZipFile(io.BytesIO(package)) as archive:
            names = archive.namelist()
            roots = {PurePosixPath(name).parts[0] for name in names if PurePosixPath(name).parts}
            if len(roots) != 1 or len(names) != len(set(names)):
                raise PackageBuildError("PACKAGE_PREVIOUS_RESULT_INVALID")
            root = next(iter(roots))
            data = {
                PurePosixPath(*PurePosixPath(name).parts[1:]).as_posix(): archive.read(name)
                for name in names
            }
            report_raw = data["REPORT/RESULT.json"]
            manifest = json.loads(data["MANIFEST.json"])
            report = json.loads(report_raw)
    except (KeyError, OSError, UnicodeError, ValueError, zipfile.BadZipFile, json.JSONDecodeError) as exc:
        raise PackageBuildError("PACKAGE_PREVIOUS_RESULT_INVALID") from exc
    manifest_files = manifest.get("files")
    if (
        manifest.get("root_name") != root
        or type(manifest_files) is not dict
        or set(manifest_files) != set(data) - {"MANIFEST.json", "SHA256SUMS.txt"}
        or any(
            record != {
                "bytes": len(data[name]),
                "sha256": hashlib.sha256(data[name]).hexdigest(),
                "mode": "0644",
            }
            for name, record in manifest_files.items()
        )
        or type(report.get("result_tree")) is not str
        or re.fullmatch(r"[0-9a-f]{40}", report["result_tree"]) is None
    ):
        raise PackageBuildError("PACKAGE_PREVIOUS_RESULT_INVALID")
    sums: dict[str, str] = {}
    for line in data["SHA256SUMS.txt"].decode("utf-8").splitlines():
        match = SUM_RE.fullmatch(line)
        if match is None or match.group(2) in sums:
            raise PackageBuildError("PACKAGE_PREVIOUS_RESULT_INVALID")
        sums[match.group(2)] = match.group(1)
    if set(sums) != set(data) - {"SHA256SUMS.txt"} or any(
        hashlib.sha256(data[name]).hexdigest() != digest for name, digest in sums.items()
    ):
        raise PackageBuildError("PACKAGE_PREVIOUS_RESULT_INVALID")
    result_patch = data.get("SOURCE/result.patch")
    if require_result_patch and not result_patch:
        raise PackageBuildError("PACKAGE_PREVIOUS_RESULT_INVALID")
    record = {
        "generation": generation,
        "package_sha256": hashlib.sha256(package).hexdigest(),
        "result_tree": report["result_tree"],
    }
    return (
        record,
        package,
        result_patch,
        data.get("SOURCE/helper1_v2_baseline_390af710.bundle"),
        data.get("SOURCE/previous_result_package.zip"),
    )


def _predecessor_to_result_patch(
    paths: tuple[str, ...],
    predecessor_patch: bytes,
    predecessor_tree: str,
    expected_result_tree: str,
    temporary: Path,
) -> tuple[bytes, tuple[str, ...]]:
    checkout = temporary / "predecessor-to-result"
    patch_path = temporary / "predecessor-result.patch"
    _write(patch_path, predecessor_patch)
    _run(("git", "clone", "--quiet", "--no-hardlinks", str(ROOT), str(checkout)), cwd=temporary)
    _run(("git", "checkout", "--quiet", "--detach", "HEAD"), cwd=checkout)
    _run(("git", "apply", "--index", str(patch_path)), cwd=checkout)
    if _run(("git", "write-tree"), cwd=checkout).decode("ascii").strip() != predecessor_tree:
        raise PackageBuildError("PACKAGE_PREDECESSOR_TREE_MISMATCH")
    for name in paths:
        destination = checkout / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / name, destination)
    _run(("git", "add", "-A", "--", *paths), cwd=checkout)
    result_tree = _run(("git", "write-tree"), cwd=checkout).decode("ascii").strip()
    if result_tree != expected_result_tree:
        raise PackageBuildError("PACKAGE_SUCCESSOR_TREE_MISMATCH")
    changed = tuple(
        item.decode("utf-8")
        for item in _run(
            ("git", "diff", "--cached", "--name-only", "-z", predecessor_tree),
            cwd=checkout,
        ).split(b"\0")
        if item
    )
    patch = _run(
        ("git", "diff", "--cached", "--binary", "--full-index", predecessor_tree),
        cwd=checkout,
    )
    if not patch or not changed:
        raise PackageBuildError("PACKAGE_SUCCESSOR_PATCH_EMPTY")
    return patch, changed


def _verify_equivalence(patch: bytes, overlay: bytes, expected_tree: str, temporary: Path) -> None:
    patch_path = temporary / "result.patch"
    overlay_path = temporary / "overlay.tar.gz"
    _write(patch_path, patch)
    _write(overlay_path, overlay)
    observed: list[str] = []
    for lane in ("patch", "tar"):
        checkout = temporary / lane
        _run(("git", "clone", "--quiet", "--no-hardlinks", str(ROOT), str(checkout)), cwd=temporary)
        _run(("git", "checkout", "--quiet", "--detach", "HEAD"), cwd=checkout)
        if lane == "patch":
            _run(("git", "apply", "--index", str(patch_path)), cwd=checkout)
        else:
            with tarfile.open(overlay_path, "r:gz") as archive:
                for member in archive.getmembers():
                    _safe_path(member.name)
                    if not member.isfile():
                        raise PackageBuildError("PACKAGE_OVERLAY_INVALID")
                archive.extractall(checkout, filter="data")
            _run(("git", "add", "-A"), cwd=checkout)
        observed.append(_run(("git", "write-tree"), cwd=checkout).decode("ascii").strip())
    if observed != [expected_tree, expected_tree]:
        raise PackageBuildError("PACKAGE_PATCH_TAR_DIVERGENCE")


def _verify_base_to_start(
    base_bundle_path: Path,
    base_patch: bytes,
    temporary: Path,
) -> None:
    checkout = temporary / "base-to-start"
    patch_path = temporary / "base-to-start.patch"
    _write(patch_path, base_patch)
    _run(("git", "clone", "--quiet", str(base_bundle_path), str(checkout)), cwd=temporary)
    _run(("git", "checkout", "--quiet", "--detach", BASE_COMMIT), cwd=checkout)
    _run(("git", "apply", "--index", str(patch_path)), cwd=checkout)
    observed = _run(("git", "write-tree"), cwd=checkout).decode("ascii").strip()
    if observed != START_TREE:
        raise PackageBuildError("PACKAGE_BASE_RECONSTRUCTION_DIVERGENCE")


def _canonical(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _source_set_digest(paths: tuple[str, ...]) -> str:
    inventory = {
        path: hashlib.sha256((ROOT / path).read_bytes()).hexdigest()
        for path in sorted(paths)
    }
    return hashlib.sha256(_canonical(inventory)).hexdigest()


def _junit_test_ids(raw: bytes) -> set[str]:
    try:
        root = ET.fromstring(raw)
    except ET.ParseError as exc:
        raise PackageBuildError("PACKAGE_TEST_REPORT_INVALID") from exc
    identifiers = {
        "python:" + "::".join(
            (
                case.get("file", ""),
                case.get("classname", ""),
                case.get("name", ""),
            )
        )
        for case in root.iter("testcase")
    }
    if "python::::" in identifiers:
        raise PackageBuildError("PACKAGE_TEST_REPORT_INVALID")
    return identifiers


def _vitest_test_ids(raw: bytes) -> set[str]:
    try:
        report = json.loads(raw)
        identifiers = {
            "desktop:"
            + str(result.get("name", ""))
            + "::"
            + str(assertion["fullName"])
            + f"::occurrence-{index}"
            for result in report["testResults"]
            for index, assertion in enumerate(result["assertionResults"])
        }
    except (KeyError, TypeError, UnicodeError, ValueError, json.JSONDecodeError) as exc:
        raise PackageBuildError("PACKAGE_TEST_REPORT_INVALID") from exc
    if any(identifier.endswith("::") for identifier in identifiers):
        raise PackageBuildError("PACKAGE_TEST_REPORT_INVALID")
    return identifiers


def _zip_info(name: str) -> zipfile.ZipInfo:
    info = zipfile.ZipInfo(f"{PACKAGE_ROOT}/{name}", ZIP_TIME)
    info.create_system = 3
    info.external_attr = (0o100644 & 0xFFFF) << 16
    info.compress_type = zipfile.ZIP_DEFLATED
    return info


def build(
    output: Path,
    evidence_path: Path,
    base_bundle_path: Path,
    previous_result_package_path: Path,
    rollback_predecessor_package_path: Path,
) -> str:
    if output.suffix.lower() != ".zip" or output.exists():
        raise PackageBuildError("PACKAGE_OUTPUT_INVALID")
    if not evidence_path.is_file() or evidence_path.is_symlink():
        raise PackageBuildError("PACKAGE_TEST_EVIDENCE_MISSING")
    if not base_bundle_path.is_file() or base_bundle_path.is_symlink():
        raise PackageBuildError("PACKAGE_BASE_BUNDLE_MISSING")
    base_bundle = base_bundle_path.read_bytes()
    if hashlib.sha256(base_bundle).hexdigest() != BASE_BUNDLE_SHA256:
        raise PackageBuildError("PACKAGE_BASE_BUNDLE_DIGEST_MISMATCH")
    try:
        _run(("git", "bundle", "verify", str(base_bundle_path)), cwd=ROOT)
        bundle_heads = _run(
            ("git", "bundle", "list-heads", str(base_bundle_path)),
            cwd=ROOT,
        ).decode("ascii").splitlines()
    except (PackageBuildError, UnicodeError) as exc:
        raise PackageBuildError("PACKAGE_BASE_BUNDLE_INVALID") from exc
    if bundle_heads != [f"{BASE_COMMIT} HEAD"]:
        raise PackageBuildError("PACKAGE_BASE_BUNDLE_IDENTITY_MISMATCH")
    chain_policy = _load_chain_contract()
    (
        predecessor,
        previous_result_package,
        predecessor_result_patch,
        predecessor_base_bundle,
        embedded_rollback_package,
    ) = (
        _candidate_package_material(
            previous_result_package_path,
            generation=PREDECESSOR_GENERATION,
            require_result_patch=True,
        )
    )
    rollback, rollback_package, _, _, _ = _candidate_package_material(
        rollback_predecessor_package_path,
        generation=ROLLBACK_GENERATION,
        require_result_patch=False,
    )
    producer_contract = chain_policy["producer_package_contract"]
    if (
        predecessor != producer_contract["immediate_predecessor"]
        or rollback != producer_contract["rollback_record"]
        or predecessor["package_sha256"] == rollback["package_sha256"]
        or predecessor["result_tree"] == rollback["result_tree"]
    ):
        raise PackageBuildError("PACKAGE_CHAIN_RECORDS_NOT_DISTINCT")
    if predecessor_base_bundle != base_bundle or embedded_rollback_package != rollback_package:
        raise PackageBuildError("PACKAGE_CHAIN_EMBEDDED_MATERIAL_MISMATCH")
    candidate_descriptor = {
        "schema_version": "butler.helper1.handoff-chain-candidate.v1",
        "chain_id": CHAIN_ID,
        "successor_generation": CHAIN_GENERATION,
        "immediate_predecessor": predecessor,
        "rollback_record": rollback,
        "authority_state": "UNCONFIGURED",
        "signature_state": "MISSING",
        "provenance_state": "UNVERIFIED",
    }
    candidate_descriptor_material = _canonical(candidate_descriptor)
    try:
        evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise PackageBuildError("PACKAGE_TEST_EVIDENCE_INVALID") from exc
    if evidence.get("schema_version") != "butler.helper1.test-evidence-index.v1":
        raise PackageBuildError("PACKAGE_TEST_EVIDENCE_INVALID")
    lanes = evidence.get("lanes")
    checks = evidence.get("checks")
    if type(lanes) is not list or type(checks) is not list or not lanes or not checks:
        raise PackageBuildError("PACKAGE_TEST_EVIDENCE_INVALID")
    if evidence.get("all_required_checks_passed") is not True:
        raise PackageBuildError("PACKAGE_REQUIRED_CHECK_FAILED")
    if evidence.get("required_lanes_blocked") != 1:
        raise PackageBuildError("PACKAGE_REQUIRED_LANE_STATE_INVALID")
    head_tree = _run(("git", "rev-parse", "HEAD^{tree}"), cwd=ROOT).decode("ascii").strip()
    if head_tree != START_TREE:
        raise PackageBuildError("PACKAGE_START_TREE_MISMATCH")
    paths = _changed_paths()
    if len(paths) != 26:
        raise PackageBuildError("PACKAGE_CHANGESET_COUNT_INVALID")
    with tempfile.TemporaryDirectory(prefix="helper1-v51-build-") as name:
        temporary = Path(name)
        result_tree, patch = _result_material(paths, temporary)
        base_to_start = _base_to_start_patch()
        overlay = _overlay(paths)
        _verify_equivalence(patch, overlay, result_tree, temporary)
        _verify_base_to_start(base_bundle_path, base_to_start, temporary)
        predecessor_to_result, successor_paths = _predecessor_to_result_patch(
            paths,
            predecessor_result_patch,
            str(predecessor["result_tree"]),
            result_tree,
            temporary,
        )
    if evidence.get("source_tree") != result_tree:
        raise PackageBuildError("PACKAGE_EVIDENCE_TREE_MISMATCH")
    files: dict[str, bytes] = {
        "SOURCE/result.patch": patch,
        "SOURCE/base_to_start.patch": base_to_start,
        "SOURCE/predecessor_to_result.patch": predecessor_to_result,
        "SOURCE/working_tree_overlay.tar.gz": overlay,
        "SOURCE/CHANGED_FILES.txt": ("\n".join(paths) + "\n").encode("utf-8"),
        "SOURCE/SUCCESSOR_CHANGED_FILES.txt": ("\n".join(successor_paths) + "\n").encode("utf-8"),
        "SOURCE/previous_result_package.zip": previous_result_package,
        "SOURCE/candidate_chain_descriptor.json": candidate_descriptor_material,
        "EVIDENCE/test-evidence-index-v1.json": _canonical(evidence),
        "VERIFY.py": (ROOT / "scripts/verify_helper1_v51_package.py").read_bytes(),
    }
    report_names = {
        "python-helper1-v4-original": "python-helper1-v4-original.junit.xml",
        "python-helper1-v51-targeted": "python-helper1-v51-targeted.junit.xml",
        "python-helper1-protected-replay": "python-helper1-protected-replay.junit.xml",
        "desktop-helper1-v51": "desktop-helper1-v51.vitest.json",
    }
    test_ids_by_lane: dict[str, set[str]] = {}
    for lane in lanes:
        if type(lane) is not dict:
            raise PackageBuildError("PACKAGE_TEST_EVIDENCE_INVALID")
        report_name = report_names.get(lane.get("lane_id"))
        if report_name is None:
            if lane.get("report_sha256") is not None:
                raise PackageBuildError("PACKAGE_TEST_REPORT_UNEXPECTED")
            continue
        report_path = evidence_path.parent / report_name
        if not report_path.is_file() or report_path.is_symlink():
            raise PackageBuildError("PACKAGE_TEST_REPORT_MISSING")
        report_bytes = report_path.read_bytes()
        if hashlib.sha256(report_bytes).hexdigest() != lane.get("report_sha256"):
            raise PackageBuildError("PACKAGE_TEST_REPORT_DIGEST_MISMATCH")
        files[f"EVIDENCE/{report_name}"] = report_bytes
        lane_id = str(lane["lane_id"])
        test_ids = (
            _vitest_test_ids(report_bytes)
            if report_name.endswith(".json")
            else _junit_test_ids(report_bytes)
        )
        if len(test_ids) != int(lane.get("collected", -1)):
            raise PackageBuildError("PACKAGE_TEST_ID_COUNT_MISMATCH")
        test_ids_by_lane[lane_id] = test_ids
    for record in (*lanes, *checks):
        if type(record) is not dict:
            raise PackageBuildError("PACKAGE_TEST_EVIDENCE_INVALID")
        for stream in ("stdout", "stderr"):
            relative = record.get(f"{stream}_path")
            digest = record.get(f"{stream}_sha256")
            if relative is None:
                if digest != hashlib.sha256(b"").hexdigest():
                    raise PackageBuildError("PACKAGE_RAW_OUTPUT_STATE_INVALID")
                continue
            if type(relative) is not str or not relative.startswith("raw/"):
                raise PackageBuildError("PACKAGE_RAW_OUTPUT_PATH_INVALID")
            raw_path = evidence_path.parent / relative
            if not raw_path.is_file() or raw_path.is_symlink():
                raise PackageBuildError("PACKAGE_RAW_OUTPUT_MISSING")
            raw = raw_path.read_bytes()
            if hashlib.sha256(raw).hexdigest() != digest:
                raise PackageBuildError("PACKAGE_RAW_OUTPUT_DIGEST_MISMATCH")
            files[f"EVIDENCE/{relative}"] = raw
    totals = {
        key: sum(int(lane.get(key, 0)) for lane in lanes)
        for key in ("collected", "passed", "failed", "errors", "skipped", "blocked")
    }
    executed_ids = [identifier for values in test_ids_by_lane.values() for identifier in values]
    unique_test_ids = set(executed_ids)
    counted_execution_total = len(executed_ids)
    if counted_execution_total != totals["collected"]:
        raise PackageBuildError("PACKAGE_TEST_EXECUTION_COUNT_MISMATCH")
    v4_acceptance = [lane for lane in lanes if lane.get("lane_id") == "python-helper1-v4-original"]
    v51_acceptance = [lane for lane in lanes if lane.get("lane_id") == "python-helper1-v51-targeted"]
    replay_acceptance = [
        lane for lane in lanes if lane.get("lane_id") == "python-helper1-protected-replay"
    ]
    if len(v4_acceptance) != 1 or len(v51_acceptance) != 1 or len(replay_acceptance) != 1:
        raise PackageBuildError("PACKAGE_ACCEPTANCE_EVIDENCE_INVALID")
    v4_counts = {
        key: int(v4_acceptance[0].get(key, -1))
        for key in ("collected", "passed", "failed", "errors", "skipped")
    }
    v51_counts = {
        key: int(v51_acceptance[0].get(key, -1))
        for key in ("collected", "passed", "failed", "errors", "skipped")
    }
    replay_counts = {
        key: int(replay_acceptance[0].get(key, -1))
        for key in ("collected", "passed", "failed", "errors", "skipped")
    }
    if (
        v4_counts["collected"] != 243
        or v51_counts["collected"] != 149
        or replay_counts["collected"] != 24
    ):
        raise PackageBuildError("PACKAGE_ACCEPTANCE_COUNT_MISMATCH")
    report = {
        "schema_version": "butler.helper1.protected-verifier-closure-result.v1",
        "base_commit": BASE_COMMIT,
        "base_bundle_sha256": BASE_BUNDLE_SHA256,
        "start_tree": START_TREE,
        "handoff_chain_id": CHAIN_ID,
        "handoff_generation": CHAIN_GENERATION,
        "chain_authority_state": "UNCONFIGURED",
        "chain_signature_state": "MISSING",
        "chain_provenance_state": "UNVERIFIED",
        "candidate_chain_descriptor_sha256": hashlib.sha256(candidate_descriptor_material).hexdigest(),
        "previous_result_tree": predecessor["result_tree"],
        "previous_result_package_sha256": predecessor["package_sha256"],
        "rollback_fixture_tree": rollback["result_tree"],
        "rollback_fixture_package_sha256": rollback["package_sha256"],
        "result_tree": result_tree,
        "v4_input_sha256": V4_INPUT_SHA256,
        "changed_file_count": len(paths),
        "patch_tar_same_tree": True,
        "base_to_start_verified": True,
        "changed_files_verified": True,
        "start_predecessor_result_chain_verified": True,
        "protection_policy_enabled": 0,
        "code_pass": 0,
        "product_release_allowed": 0,
        "runtime_activation_allowed": 0,
        "production_claim_allowed": 0,
        "test_evidence_all_required_lanes_passed": bool(evidence.get("all_required_lanes_passed")),
        "test_evidence_all_required_checks_passed": True,
        "test_totals": totals,
        "test_identity_counts": {
            "unique_tests": len(unique_test_ids),
            "execution_total_including_duplicates": counted_execution_total,
            "duplicate_executions": counted_execution_total - len(unique_test_ids),
            "counting_method": "REPORT_NODE_ID_UNION_V1",
        },
        "v4_original_acceptance": v4_counts,
        "v51_targeted_acceptance": v51_counts,
        "protected_replay_acceptance": replay_counts,
        "required_lanes_blocked": int(evidence["required_lanes_blocked"]),
        "implementation_map": {
            "fix1_observed_search_and_index": "butler_pc_core/helper1/service.py",
            "fix2_false_abstention_denominator": "butler_pc_core/helper1/approval_closure.py",
            "fix3_deterministic_patch_tar": "scripts/build_helper1_v51_package.py",
            "protected_verifier_a4_closure": "scripts/ci/helper1_trusted_verifier.py",
            "durable_replay_store": "butler_pc_core/helper1/replay_store.py",
            "preconnect_endpoint_pinning": "butler_pc_core/helper1/replay_store.py",
            "protected_handoff_chain_authority": "contracts/helper1/trusted-verifier-policy-v1.json",
            "protected_replay_workflow_binding": ".github/workflows/helper1-v2-trusted-verifier.yml",
            "protected_replay_database_probe": "scripts/ci/helper1_postgresql_replay_probe.py",
            "fixed_path_producer_package": "scripts/ci/helper1_producer_package.py",
        },
        "canonical_vector_digest": _source_set_digest(CANONICAL_VECTOR_PATHS),
        "trust_policy_digest": hashlib.sha256((ROOT / APPROVAL_POLICY_PATH).read_bytes()).hexdigest(),
        "unverified_items": [
            "macOS native required lane",
            "real native asset and locked Xcode scheme",
            "protected remote CI",
            "protected PostgreSQL replay environment and two-workflow-run E2E",
            "production signing identity and trust root",
            "protected signed handoff chain authority",
        ],
        "blockers": [
            "MACOS_NATIVE_LANE_NOT_CONFIGURED",
            "PROTECTED_REPLAY_ENVIRONMENT_NOT_PROVISIONED",
            "HANDOFF_CHAIN_AUTHORITY_NOT_CONFIGURED",
        ],
        "raw_diagnostics_policy": "CONTAINED_RAW_STDOUT_STDERR_WITH_SHA256",
        "publication": {"branch": False, "commit": False, "push": False, "pr": False},
    }
    files["REPORT/RESULT.json"] = _canonical(report)
    manifest = {
        "schema_version": "butler.helper1.protected-verifier-closure-package.v1",
        "root_name": PACKAGE_ROOT,
        "start_tree": START_TREE,
        "result_tree": result_tree,
        "files": {
            name: {"bytes": len(data), "sha256": hashlib.sha256(data).hexdigest(), "mode": "0644"}
            for name, data in sorted(files.items())
        },
    }
    files["MANIFEST.json"] = _canonical(manifest)
    sums = "".join(f"{hashlib.sha256(data).hexdigest()}  {name}\n" for name, data in sorted(files.items()))
    files["SHA256SUMS.txt"] = sums.encode("utf-8")
    output.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    temporary_output = output.with_suffix(output.suffix + ".tmp")
    with zipfile.ZipFile(temporary_output, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for name, data in sorted(files.items()):
            archive.writestr(_zip_info(name), data)
    os.replace(temporary_output, output)
    return hashlib.sha256(output.read_bytes()).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--test-evidence", required=True, type=Path)
    parser.add_argument("--base-bundle", required=True, type=Path)
    parser.add_argument("--previous-result-package", required=True, type=Path)
    parser.add_argument("--rollback-predecessor-package", required=True, type=Path)
    args = parser.parse_args()
    try:
        digest = build(
            args.output,
            args.test_evidence,
            args.base_bundle,
            args.previous_result_package,
            args.rollback_predecessor_package,
        )
    except PackageBuildError as exc:
        print("HELPER1_V51_PACKAGE_BUILD_OK=0")
        print(f"ERROR_CODE={exc}")
        return 1
    print("HELPER1_V51_PACKAGE_BUILD_OK=1")
    print(f"PACKAGE_SHA256={digest}")
    print("ERROR_CODE=NONE")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
