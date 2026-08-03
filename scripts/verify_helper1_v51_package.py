#!/usr/bin/env python3
"""Independent, fail-closed structural verifier for a Helper1 v5.1 ZIP."""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import re
import stat
import subprocess
import sys
import tarfile
import tempfile
import unicodedata
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path, PurePosixPath
from typing import Callable

FIXED_ZIP_TIME = (1980, 1, 1, 0, 0, 0)
SUM_RE = re.compile(r"^([0-9a-f]{64})  ([^\x00\r\n]+)$")
BASE_COMMIT = "390af710bdc76a58be3158b6bcbf0638d62b49a4"
BASE_BUNDLE_SHA256 = "53fccfead8b2089dc3b595ed4ce7f01e9d3e9664ec67faca045fa7dfdb4ed41d"
START_TREE = "243074f44cf6883a5ad9665a2c40132c7c42a535"


def _path(value: str) -> str | None:
    path = PurePosixPath(value)
    if (
        not value
        or value != unicodedata.normalize("NFC", value)
        or path.is_absolute()
        or "\\" in value
        or "\x00" in value
        or any(part in {"", ".", ".."} for part in path.parts)
    ):
        return None
    return path.as_posix()


def _tar_errors(raw: bytes) -> set[str]:
    errors: set[str] = set()
    names: list[str] = []
    folded: set[str] = set()
    try:
        with tarfile.open(fileobj=io.BytesIO(raw), mode="r:gz") as archive:
            for member in archive.getmembers():
                normalized = _path(member.name)
                if normalized is None:
                    errors.add("PACKAGE_OVERLAY_PATH_INVALID")
                    continue
                if normalized.startswith("__MACOSX/") or PurePosixPath(normalized).name.startswith("._"):
                    errors.add("PACKAGE_OVERLAY_APPLEDOUBLE_FORBIDDEN")
                key = normalized.casefold()
                if normalized in names or key in folded:
                    errors.add("PACKAGE_OVERLAY_PATH_COLLISION")
                names.append(normalized)
                folded.add(key)
                if not member.isfile() or member.issym() or member.islnk():
                    errors.add("PACKAGE_OVERLAY_TYPE_INVALID")
                if member.uid != 0 or member.gid != 0 or member.mtime != 0:
                    errors.add("PACKAGE_OVERLAY_METADATA_INVALID")
                if member.mode not in {0o644, 0o755} or member.pax_headers:
                    errors.add("PACKAGE_OVERLAY_METADATA_INVALID")
            if names != sorted(names):
                errors.add("PACKAGE_OVERLAY_ORDER_INVALID")
    except (OSError, tarfile.TarError):
        errors.add("PACKAGE_OVERLAY_INVALID")
    return errors


def _report_test_ids(path: str, raw: bytes) -> set[str]:
    if path.endswith(".json"):
        report = json.loads(raw)
        return {
            "desktop:"
            + str(result.get("name", ""))
            + "::"
            + str(assertion["fullName"])
            + f"::occurrence-{index}"
            for result in report["testResults"]
            for index, assertion in enumerate(result["assertionResults"])
        }
    root = ET.fromstring(raw)
    return {
        "python:" + "::".join(
            (case.get("file", ""), case.get("classname", ""), case.get("name", ""))
        )
        for case in root.iter("testcase")
    }


def _run_git(arguments: tuple[str, ...], cwd: Path) -> str:
    completed = subprocess.run(
        ("git", *arguments),
        cwd=cwd,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=120,
        check=False,
    )
    if completed.returncode != 0:
        raise RuntimeError("PACKAGE_GIT_RECONSTRUCTION_FAILED")
    return completed.stdout.decode("utf-8").strip()


def _reconstruct_product_trees(
    base_bundle: bytes,
    base_to_start_patch: bytes,
    predecessor_result_patch: bytes,
    predecessor_to_result_patch: bytes,
    result_patch: bytes,
    overlay: bytes,
    expected_predecessor_tree: str,
    expected_result_tree: str,
    expected_changed_paths: tuple[str, ...],
    expected_successor_paths: tuple[str, ...],
) -> bool:
    try:
        with tempfile.TemporaryDirectory(prefix="helper1-package-verify-") as name:
            temporary = Path(name)
            bundle_path = temporary / "base.bundle"
            base_patch_path = temporary / "base-to-start.patch"
            predecessor_patch_path = temporary / "predecessor-result.patch"
            successor_patch_path = temporary / "predecessor-to-result.patch"
            result_patch_path = temporary / "result.patch"
            bundle_path.write_bytes(base_bundle)
            base_patch_path.write_bytes(base_to_start_patch)
            predecessor_patch_path.write_bytes(predecessor_result_patch)
            successor_patch_path.write_bytes(predecessor_to_result_patch)
            result_patch_path.write_bytes(result_patch)
            heads = _run_git(("bundle", "list-heads", str(bundle_path)), temporary)
            if heads != f"{BASE_COMMIT} HEAD":
                return False

            def prepare_start(lane: str) -> Path:
                checkout = temporary / lane
                _run_git(("clone", "--quiet", str(bundle_path), str(checkout)), temporary)
                _run_git(("bundle", "verify", str(bundle_path)), checkout)
                _run_git(("checkout", "--quiet", "--detach", BASE_COMMIT), checkout)
                _run_git(("apply", "--index", str(base_patch_path)), checkout)
                if _run_git(("write-tree",), checkout) != START_TREE:
                    raise RuntimeError("PACKAGE_START_TREE_RECONSTRUCTION_FAILED")
                return checkout

            patch_checkout = prepare_start("patch")
            _run_git(("apply", "--index", str(result_patch_path)), patch_checkout)
            patch_changed = tuple(
                item
                for item in _run_git(
                    ("diff", "--cached", "--name-only", "-z", START_TREE),
                    patch_checkout,
                ).split("\0")
                if item
            )
            patch_tree = _run_git(("write-tree",), patch_checkout)

            lineage_checkout = prepare_start("lineage")
            _run_git(("apply", "--index", str(predecessor_patch_path)), lineage_checkout)
            if _run_git(("write-tree",), lineage_checkout) != expected_predecessor_tree:
                return False
            _run_git(("apply", "--index", str(successor_patch_path)), lineage_checkout)
            successor_changed = tuple(
                item
                for item in _run_git(
                    ("diff", "--cached", "--name-only", "-z", expected_predecessor_tree),
                    lineage_checkout,
                ).split("\0")
                if item
            )
            lineage_tree = _run_git(("write-tree",), lineage_checkout)

            overlay_checkout = prepare_start("overlay")
            with tarfile.open(fileobj=io.BytesIO(overlay), mode="r:gz") as archive:
                overlay_names = tuple(member.name for member in archive.getmembers())
                if overlay_names != expected_changed_paths:
                    return False
                archive.extractall(overlay_checkout, filter="data")
            _run_git(("add", "-A"), overlay_checkout)
            overlay_changed = tuple(
                item
                for item in _run_git(
                    ("diff", "--cached", "--name-only", "-z", START_TREE),
                    overlay_checkout,
                ).split("\0")
                if item
            )
            overlay_tree = _run_git(("write-tree",), overlay_checkout)
            return (
                patch_tree == expected_result_tree
                and overlay_tree == expected_result_tree
                and lineage_tree == expected_result_tree
                and patch_changed == expected_changed_paths
                and overlay_changed == expected_changed_paths
                and successor_changed == expected_successor_paths
            )
    except (OSError, RuntimeError, subprocess.TimeoutExpired, UnicodeError, tarfile.TarError):
        return False


def _canonical_anchor(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _load_chain_anchor(path: Path) -> tuple[dict[str, object], bytes] | None:
    try:
        if not path.is_file() or path.is_symlink():
            return None
        policy = json.loads(path.read_bytes())
        anchor = policy["handoff_chain_anchor"]
    except (KeyError, OSError, TypeError, ValueError, json.JSONDecodeError):
        return None
    if (
        type(policy) is not dict
        or policy.get("enabled") is not False
        or type(anchor) is not dict
        or set(anchor) != {
            "schema_version",
            "chain_id",
            "successor_generation",
            "immediate_predecessor",
            "forbidden_rollback_fixture",
        }
        or anchor.get("schema_version") != "butler.helper1.handoff-chain-anchor.v1"
    ):
        return None
    predecessor = anchor.get("immediate_predecessor")
    rollback = anchor.get("forbidden_rollback_fixture")
    generation = anchor.get("successor_generation")
    for record in (predecessor, rollback):
        if (
            type(record) is not dict
            or set(record) != {"generation", "package_sha256", "result_tree"}
            or type(record.get("generation")) is not int
            or type(record.get("package_sha256")) is not str
            or re.fullmatch(r"[0-9a-f]{64}", record["package_sha256"]) is None
            or type(record.get("result_tree")) is not str
            or re.fullmatch(r"[0-9a-f]{40}", record["result_tree"]) is None
        ):
            return None
    if (
        type(generation) is not int
        or generation < 2
        or predecessor["generation"] != generation - 1
        or rollback["generation"] >= predecessor["generation"]
    ):
        return None
    return anchor, _canonical_anchor(anchor)


def _anchored_package_material(
    package: bytes,
    expected: dict[str, object],
    *,
    require_result_patch: bool,
) -> tuple[str, bytes | None] | None:
    if hashlib.sha256(package).hexdigest() != expected["package_sha256"]:
        return None
    try:
        with zipfile.ZipFile(io.BytesIO(package)) as archive:
            names = archive.namelist()
            roots = {PurePosixPath(name).parts[0] for name in names if PurePosixPath(name).parts}
            if len(roots) != 1 or len(names) != len(set(names)):
                return None
            root = next(iter(roots))
            data = {
                PurePosixPath(*PurePosixPath(name).parts[1:]).as_posix(): archive.read(name)
                for name in names
            }
        manifest = json.loads(data["MANIFEST.json"])
        report = json.loads(data["REPORT/RESULT.json"])
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
            or report.get("result_tree") != expected["result_tree"]
        ):
            return None
        sums: dict[str, str] = {}
        for line in data["SHA256SUMS.txt"].decode("utf-8").splitlines():
            match = SUM_RE.fullmatch(line)
            if match is None or match.group(2) in sums:
                return None
            sums[match.group(2)] = match.group(1)
        if set(sums) != set(data) - {"SHA256SUMS.txt"} or any(
            hashlib.sha256(data[name]).hexdigest() != digest for name, digest in sums.items()
        ):
            return None
        result_patch = data.get("SOURCE/result.patch")
        if require_result_patch and not result_patch:
            return None
        return str(report["result_tree"]), result_patch
    except (KeyError, OSError, TypeError, UnicodeError, ValueError, zipfile.BadZipFile, json.JSONDecodeError):
        return None


def _canonical_json(value: object) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
    ).encode("utf-8")


def _zip_info(name: str) -> zipfile.ZipInfo:
    info = zipfile.ZipInfo(name, FIXED_ZIP_TIME)
    info.compress_type = zipfile.ZIP_DEFLATED
    info.create_system = 3
    info.external_attr = (stat.S_IFREG | 0o644) << 16
    return info


def _write_mutated_package(
    source: Path,
    destination: Path,
    relative_path: str,
    mutate: Callable[[bytes], bytes],
) -> bool:
    try:
        with zipfile.ZipFile(source) as archive:
            root_names = {
                PurePosixPath(item.filename).parts[0]
                for item in archive.infolist()
                if PurePosixPath(item.filename).parts
            }
            if len(root_names) != 1:
                return False
            root = next(iter(root_names))
            entries = {
                PurePosixPath(*PurePosixPath(item.filename).parts[1:]).as_posix(): archive.read(item)
                for item in archive.infolist()
            }
        original = entries.get(relative_path)
        if original is None:
            return False
        changed = mutate(original)
        if type(changed) is not bytes or changed == original:
            return False
        entries[relative_path] = changed
        manifest = json.loads(entries["MANIFEST.json"])
        manifest["files"][relative_path] = {
            "bytes": len(changed),
            "sha256": hashlib.sha256(changed).hexdigest(),
            "mode": "0644",
        }
        entries["MANIFEST.json"] = _canonical_json(manifest)
        entries["SHA256SUMS.txt"] = "".join(
            f"{hashlib.sha256(raw).hexdigest()}  {name}\n"
            for name, raw in sorted(entries.items())
            if name != "SHA256SUMS.txt"
        ).encode("utf-8")
        with zipfile.ZipFile(
            destination,
            "w",
            compression=zipfile.ZIP_DEFLATED,
            compresslevel=9,
        ) as archive:
            for name, raw in sorted(entries.items()):
                archive.writestr(_zip_info(f"{root}/{name}"), raw)
        return True
    except (KeyError, OSError, TypeError, ValueError, zipfile.BadZipFile, json.JSONDecodeError):
        return False


def _append_base_to_start_mutation(raw: bytes) -> bytes:
    separator = b"" if raw.endswith(b"\n") else b"\n"
    return raw + separator + (
        b"diff --git a/helper1-package-mutant.txt b/helper1-package-mutant.txt\n"
        b"new file mode 100644\n"
        b"--- /dev/null\n"
        b"+++ b/helper1-package-mutant.txt\n"
        b"@@ -0,0 +1 @@\n"
        b"+mutant\n"
    )


def _package_mutation_gate(
    package: str,
    chain_anchor: tuple[dict[str, object], bytes],
) -> tuple[bool, bool]:
    with tempfile.TemporaryDirectory(prefix="helper1-package-mutations-") as name:
        temporary = Path(name)
        source = Path(package)
        base_mutant = temporary / "base-to-start-mutant.zip"
        rollback_mutant = temporary / "predecessor-rollback-mutant.zip"
        try:
            with zipfile.ZipFile(source) as archive:
                rollback_name = next(
                    item
                    for item in archive.namelist()
                    if item.endswith("/EVIDENCE/chain/rollback_predecessor_10r.zip")
                )
                rollback_package = archive.read(rollback_name)
        except (OSError, StopIteration, zipfile.BadZipFile):
            return False, False
        base_created = _write_mutated_package(
            source,
            base_mutant,
            "SOURCE/base_to_start.patch",
            _append_base_to_start_mutation,
        )
        rollback_created = _write_mutated_package(
            source,
            rollback_mutant,
            "SOURCE/previous_result_package.zip",
            lambda _raw: rollback_package,
        )
        base_rejected = base_created and not verify(str(base_mutant), chain_anchor)[0]
        rollback_rejected = rollback_created and not verify(str(rollback_mutant), chain_anchor)[0]
        return base_rejected, rollback_rejected


def verify(
    package: str,
    chain_anchor: tuple[dict[str, object], bytes],
) -> tuple[bool, tuple[str, ...]]:
    errors: set[str] = set()
    anchor, anchor_material = chain_anchor
    predecessor = anchor["immediate_predecessor"]
    rollback = anchor["forbidden_rollback_fixture"]
    data: dict[str, bytes] = {}
    root = ""
    try:
        with zipfile.ZipFile(package) as archive:
            members = archive.infolist()
            if not members:
                return False, ("PACKAGE_EMPTY",)
            root_names = {
                PurePosixPath(item.filename).parts[0]
                for item in members
                if PurePosixPath(item.filename).parts
            }
            if len(root_names) != 1:
                errors.add("PACKAGE_ROOT_INVALID")
            else:
                root = next(iter(root_names))
                if _path(root) is None:
                    errors.add("PACKAGE_ROOT_INVALID")
            names: list[str] = []
            folded: set[str] = set()
            for item in members:
                normalized = _path(item.filename)
                if normalized is None:
                    errors.add("PACKAGE_PATH_INVALID")
                    continue
                key = normalized.casefold()
                if normalized in names or key in folded:
                    errors.add("PACKAGE_PATH_COLLISION")
                names.append(normalized)
                folded.add(key)
                mode = item.external_attr >> 16
                if item.is_dir() or stat.S_ISLNK(mode) or not stat.S_ISREG(mode):
                    errors.add("PACKAGE_FILE_TYPE_INVALID")
                    continue
                if stat.S_IMODE(mode) != 0o644 or item.date_time != FIXED_ZIP_TIME or item.extra:
                    errors.add("PACKAGE_METADATA_INVALID")
                path = PurePosixPath(normalized)
                if not root or len(path.parts) < 2 or path.parts[0] != root:
                    errors.add("PACKAGE_ROOT_INVALID")
                    continue
                relative = PurePosixPath(*path.parts[1:]).as_posix()
                try:
                    data[relative] = archive.read(item)
                except (OSError, RuntimeError, zipfile.BadZipFile):
                    errors.add("PACKAGE_MEMBER_READ_FAILED")
            if names != sorted(names):
                errors.add("PACKAGE_ARCHIVE_ORDER_INVALID")
    except (OSError, zipfile.BadZipFile):
        return False, ("PACKAGE_INVALID",)

    required = {
        "MANIFEST.json", "SHA256SUMS.txt", "VERIFY.py", "REPORT/RESULT.json",
        "SOURCE/result.patch", "SOURCE/base_to_start.patch", "SOURCE/predecessor_to_result.patch",
        "SOURCE/working_tree_overlay.tar.gz", "SOURCE/chain_anchor_snapshot.json",
        "SOURCE/helper1_v2_baseline_390af710.bundle",
        "SOURCE/previous_result_package.zip",
        "SOURCE/CHANGED_FILES.txt", "SOURCE/SUCCESSOR_CHANGED_FILES.txt",
        "EVIDENCE/chain/rollback_predecessor_10r.zip",
        "EVIDENCE/test-evidence-index-v1.json",
        "EVIDENCE/python-helper1-v4-original.junit.xml", "EVIDENCE/python-helper1-v51-targeted.junit.xml",
        "EVIDENCE/python-helper1-protected-replay.junit.xml",
        "EVIDENCE/desktop-helper1-v51.vitest.json",
    }
    if not required <= set(data) or any(
        name not in required and not name.startswith("EVIDENCE/raw/") for name in data
    ):
        errors.add("PACKAGE_INVENTORY_INVALID")
    try:
        manifest = json.loads(data["MANIFEST.json"])
        manifest_files = manifest.get("files")
        if (
            manifest.get("schema_version") != "butler.helper1.protected-verifier-closure-package.v1"
            or manifest.get("root_name") != root
            or type(manifest_files) is not dict
            or set(manifest_files) != set(data) - {"MANIFEST.json", "SHA256SUMS.txt"}
        ):
            errors.add("PACKAGE_MANIFEST_INVALID")
        else:
            for name, record in manifest_files.items():
                expected = {
                    "bytes": len(data[name]),
                    "sha256": hashlib.sha256(data[name]).hexdigest(),
                    "mode": "0644",
                }
                if record != expected:
                    errors.add("PACKAGE_DIGEST_MISMATCH")
        sum_lines = data["SHA256SUMS.txt"].decode("utf-8").splitlines()
        parsed_sums: dict[str, str] = {}
        for line in sum_lines:
            match = SUM_RE.fullmatch(line)
            if match is None or _path(match.group(2)) is None or match.group(2) in parsed_sums:
                errors.add("PACKAGE_SUMS_INVALID")
                continue
            parsed_sums[match.group(2)] = match.group(1)
        if set(parsed_sums) != set(data) - {"SHA256SUMS.txt"}:
            errors.add("PACKAGE_SUMS_INVALID")
        elif any(hashlib.sha256(data[name]).hexdigest() != digest for name, digest in parsed_sums.items()):
            errors.add("PACKAGE_SUMS_INVALID")
        report = json.loads(data["REPORT/RESULT.json"])
        if any(
            report.get(key) != 0
            for key in (
                "protection_policy_enabled", "code_pass", "product_release_allowed",
                "runtime_activation_allowed", "production_claim_allowed",
            )
        ):
            errors.add("PACKAGE_UNSAFE_APPROVAL_STATE")
        if (
            report.get("patch_tar_same_tree") is not True
            or report.get("required_lanes_blocked") != 1
            or report.get("raw_diagnostics_policy") != "CONTAINED_RAW_STDOUT_STDERR_WITH_SHA256"
            or type(report.get("canonical_vector_digest")) is not str
            or re.fullmatch(r"[0-9a-f]{64}", report["canonical_vector_digest"]) is None
            or type(report.get("trust_policy_digest")) is not str
            or re.fullmatch(r"[0-9a-f]{64}", report["trust_policy_digest"]) is None
            or set(report.get("implementation_map", {})) != {
                "fix1_observed_search_and_index",
                "fix2_false_abstention_denominator",
                "fix3_deterministic_patch_tar",
                "protected_verifier_a4_closure",
                "durable_replay_store",
                "preconnect_endpoint_pinning",
                "protected_handoff_chain_anchor",
                "protected_replay_workflow_binding",
                "protected_replay_database_probe",
            }
            or report.get("start_tree") != START_TREE
            or report.get("handoff_chain_id") != anchor["chain_id"]
            or report.get("handoff_generation") != anchor["successor_generation"]
            or report.get("chain_anchor_sha256") != hashlib.sha256(anchor_material).hexdigest()
            or report.get("previous_result_tree") != predecessor["result_tree"]
            or report.get("previous_result_package_sha256") != predecessor["package_sha256"]
            or report.get("rollback_fixture_tree") != rollback["result_tree"]
            or report.get("rollback_fixture_package_sha256") != rollback["package_sha256"]
            or report.get("base_to_start_verified") is not True
            or report.get("changed_files_verified") is not True
            or report.get("start_predecessor_result_chain_verified") is not True
            or report.get("changed_file_count") != 22
            or report.get("v4_original_acceptance", {}).get("passed") != 243
            or report.get("v51_targeted_acceptance", {}).get("passed") != 149
            or report.get("protected_replay_acceptance", {}).get("passed") != 15
            or report.get("base_commit") != BASE_COMMIT
            or report.get("base_bundle_sha256") != BASE_BUNDLE_SHA256
            or report.get("blockers") != [
                "MACOS_NATIVE_LANE_NOT_CONFIGURED",
                "PROTECTED_REPLAY_ENVIRONMENT_NOT_PROVISIONED",
            ]
        ):
            errors.add("PACKAGE_RESULT_CONTRACT_INVALID")
        evidence = json.loads(data["EVIDENCE/test-evidence-index-v1.json"])
        if (
            evidence.get("schema_version") != "butler.helper1.test-evidence-index.v1"
            or evidence.get("all_required_lanes_passed") is not False
            or evidence.get("all_required_checks_passed") is not True
            or evidence.get("required_lanes_blocked") != 1
            or evidence.get("source_tree") != report.get("result_tree")
        ):
            errors.add("PACKAGE_EVIDENCE_STATE_INVALID")
        report_by_lane = {
            "python-helper1-v4-original": "EVIDENCE/python-helper1-v4-original.junit.xml",
            "python-helper1-v51-targeted": "EVIDENCE/python-helper1-v51-targeted.junit.xml",
            "python-helper1-protected-replay": "EVIDENCE/python-helper1-protected-replay.junit.xml",
            "desktop-helper1-v51": "EVIDENCE/desktop-helper1-v51.vitest.json",
        }
        executed_test_ids: list[str] = []
        records = [*evidence.get("lanes", []), *evidence.get("checks", [])]
        expected_raw: set[str] = set()
        for record in records:
            if type(record) is not dict:
                errors.add("PACKAGE_EVIDENCE_STATE_INVALID")
                continue
            for stream in ("stdout", "stderr"):
                relative = record.get(f"{stream}_path")
                digest = record.get(f"{stream}_sha256")
                if relative is None:
                    if digest != hashlib.sha256(b"").hexdigest():
                        errors.add("PACKAGE_RAW_OUTPUT_STATE_INVALID")
                    continue
                path = f"EVIDENCE/{relative}"
                expected_raw.add(path)
                if path not in data or hashlib.sha256(data[path]).hexdigest() != digest:
                    errors.add("PACKAGE_RAW_OUTPUT_DIGEST_MISMATCH")
        if {name for name in data if name.startswith("EVIDENCE/raw/")} != expected_raw:
            errors.add("PACKAGE_RAW_OUTPUT_INVENTORY_INVALID")
        for lane in evidence.get("lanes", []):
            if type(lane) is not dict:
                errors.add("PACKAGE_EVIDENCE_STATE_INVALID")
                continue
            report_path = report_by_lane.get(lane.get("lane_id"))
            if report_path and hashlib.sha256(data[report_path]).hexdigest() != lane.get("report_sha256"):
                errors.add("PACKAGE_TEST_REPORT_DIGEST_MISMATCH")
            if report_path:
                test_ids = _report_test_ids(report_path, data[report_path])
                if len(test_ids) != lane.get("collected"):
                    errors.add("PACKAGE_TEST_ID_COUNT_MISMATCH")
                executed_test_ids.extend(test_ids)
        identity_counts = report.get("test_identity_counts", {})
        if identity_counts != {
            "unique_tests": len(set(executed_test_ids)),
            "execution_total_including_duplicates": len(executed_test_ids),
            "duplicate_executions": len(executed_test_ids) - len(set(executed_test_ids)),
            "counting_method": "REPORT_NODE_ID_UNION_V1",
        }:
            errors.add("PACKAGE_TEST_IDENTITY_COUNTS_INVALID")
        changed_paths_raw = data["SOURCE/CHANGED_FILES.txt"].decode("utf-8")
        changed_paths = tuple(changed_paths_raw.splitlines())
        if (
            not changed_paths_raw.endswith("\n")
            or len(changed_paths) != 22
            or changed_paths != tuple(sorted(changed_paths))
            or len(set(changed_paths)) != len(changed_paths)
            or any(_path(path) != path for path in changed_paths)
        ):
            errors.add("PACKAGE_CHANGED_FILES_INVALID")
        successor_paths_raw = data["SOURCE/SUCCESSOR_CHANGED_FILES.txt"].decode("utf-8")
        successor_paths = tuple(successor_paths_raw.splitlines())
        if (
            not successor_paths_raw.endswith("\n")
            or not successor_paths
            or successor_paths != tuple(sorted(successor_paths))
            or len(set(successor_paths)) != len(successor_paths)
            or any(_path(path) != path for path in successor_paths)
            or not set(successor_paths) <= set(changed_paths)
        ):
            errors.add("PACKAGE_SUCCESSOR_CHANGED_FILES_INVALID")
        errors.update(_tar_errors(data["SOURCE/working_tree_overlay.tar.gz"]))
        if hashlib.sha256(data["SOURCE/helper1_v2_baseline_390af710.bundle"]).hexdigest() != BASE_BUNDLE_SHA256:
            errors.add("PACKAGE_BASE_BUNDLE_DIGEST_MISMATCH")
        if data["SOURCE/chain_anchor_snapshot.json"] != anchor_material:
            errors.add("PACKAGE_CHAIN_ANCHOR_SNAPSHOT_MISMATCH")
        previous_material = _anchored_package_material(
            data["SOURCE/previous_result_package.zip"],
            predecessor,
            require_result_patch=True,
        )
        rollback_material = _anchored_package_material(
            data["EVIDENCE/chain/rollback_predecessor_10r.zip"],
            rollback,
            require_result_patch=False,
        )
        if previous_material is None or previous_material[0] != report.get("previous_result_tree"):
            errors.add("PACKAGE_PREVIOUS_RESULT_INVALID")
        if rollback_material is None or rollback_material[0] != report.get("rollback_fixture_tree"):
            errors.add("PACKAGE_ROLLBACK_FIXTURE_INVALID")
        if (
            previous_material is not None
            and "PACKAGE_CHANGED_FILES_INVALID" not in errors
            and "PACKAGE_SUCCESSOR_CHANGED_FILES_INVALID" not in errors
            and not _reconstruct_product_trees(
                data["SOURCE/helper1_v2_baseline_390af710.bundle"],
                data["SOURCE/base_to_start.patch"],
                previous_material[1],
                data["SOURCE/predecessor_to_result.patch"],
                data["SOURCE/result.patch"],
                data["SOURCE/working_tree_overlay.tar.gz"],
                str(predecessor["result_tree"]),
                str(report.get("result_tree", "")),
                changed_paths,
                successor_paths,
            )
        ):
            errors.add("PACKAGE_TREE_RECONSTRUCTION_FAILED")
    except (KeyError, TypeError, UnicodeError, ValueError, json.JSONDecodeError, ET.ParseError):
        errors.add("PACKAGE_CONTENT_INVALID")
    return not errors, tuple(sorted(errors))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("package")
    parser.add_argument("--chain-anchor", required=True, type=Path)
    args = parser.parse_args()
    chain_anchor = _load_chain_anchor(args.chain_anchor)
    if chain_anchor is None:
        print("HELPER1_V51_PACKAGE_VERIFY_OK=0")
        print("PACKAGE_MUTATION_BASE_TO_START_REJECTED=0")
        print("PACKAGE_MUTATION_PREDECESSOR_ROLLBACK_REJECTED=0")
        print("ERROR_CODE=PACKAGE_CHAIN_ANCHOR_INVALID")
        return 1
    ok, errors = verify(args.package, chain_anchor)
    base_mutant_rejected = False
    rollback_mutant_rejected = False
    if ok:
        base_mutant_rejected, rollback_mutant_rejected = _package_mutation_gate(
            args.package,
            chain_anchor,
        )
        if not base_mutant_rejected or not rollback_mutant_rejected:
            ok = False
            errors = (*errors, "PACKAGE_MUTATION_SURVIVED")
    print(f"HELPER1_V51_PACKAGE_VERIFY_OK={int(ok)}")
    print(f"PACKAGE_MUTATION_BASE_TO_START_REJECTED={int(base_mutant_rejected)}")
    print(f"PACKAGE_MUTATION_PREDECESSOR_ROLLBACK_REJECTED={int(rollback_mutant_rejected)}")
    for code in errors:
        print(f"ERROR_CODE={code}")
    if not errors:
        print("ERROR_CODE=NONE")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
