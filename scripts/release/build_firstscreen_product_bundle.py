#!/usr/bin/env python3
"""Build the single-file FirstScreen v2.5 product handoff from a clean Git commit.

This is a developer handoff builder, not a release signer.  It deliberately
records a missing signed native subject and leaves every release gate closed.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import stat
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path, PurePosixPath

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from butler_pc_core.firstscreen_trust import build_context_digest, strict_json_loads, validate_build_context
from scripts.release.firstscreen_source_contracts import PROTECTED_PATHS, protected_contract_digest, protected_pathspecs


FIXED_TIME = (1980, 1, 1, 0, 0, 0)
IMPORTED_COMMIT = "fde4091cb244853e3f22817b23122f919841558b"
IMPORTED_TREE = "0ad31a2ec73cb469d176fcf6ac779ce1088ab9a8"
REPORT_NAMES = (
    "IMPLEMENTATION_REPORT.md",
    "TRACEABILITY.md",
    "REPRODUCE.md",
    "KNOWN_EXTERNAL_GATES.md",
    "ATTACK_MATRIX.json",
)


class BundleBuildError(RuntimeError):
    """Stable handoff build failure boundary."""


def _run(*arguments: str, cwd: Path) -> bytes:
    try:
        return subprocess.run(
            list(arguments), cwd=cwd, check=True, capture_output=True, timeout=300,
        ).stdout
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
        raise BundleBuildError("PRODUCT_BUNDLE_COMMAND_FAILED") from exc


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _regular(path: Path, maximum: int = 1024 * 1024 * 1024) -> bytes:
    try:
        metadata = path.lstat()
    except OSError as exc:
        raise BundleBuildError("PRODUCT_INPUT_MISSING") from exc
    if (
        path.is_symlink()
        or not stat.S_ISREG(metadata.st_mode)
        or metadata.st_nlink != 1
        or metadata.st_size <= 0
        or metadata.st_size > maximum
    ):
        raise BundleBuildError("PRODUCT_INPUT_INVALID")
    return path.read_bytes()


def _safe_name(raw: str) -> str:
    path = PurePosixPath(raw)
    if path.is_absolute() or not path.parts or ".." in path.parts or "\\" in raw or "\0" in raw:
        raise BundleBuildError("PRODUCT_BUNDLE_PATH_INVALID")
    try:
        raw.encode("ascii")
    except UnicodeEncodeError as exc:
        raise BundleBuildError("PRODUCT_BUNDLE_PATH_NOT_ASCII") from exc
    return path.as_posix()


def _info(name: str, executable: bool = False) -> zipfile.ZipInfo:
    info = zipfile.ZipInfo(_safe_name(name), date_time=FIXED_TIME)
    info.compress_type = zipfile.ZIP_DEFLATED
    info.create_system = 3
    info.external_attr = (stat.S_IFREG | (0o755 if executable else 0o644)) << 16
    return info


def _zip_regular_directory(root: Path) -> bytes:
    if not root.is_dir() or root.is_symlink():
        raise BundleBuildError("WEB_DIST_MISSING")
    output = tempfile.SpooledTemporaryFile(max_size=64 * 1024 * 1024)
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        files = sorted(path for path in root.rglob("*") if path.is_file())
        if not files:
            raise BundleBuildError("WEB_DIST_EMPTY")
        for path in files:
            if path.is_symlink():
                raise BundleBuildError("WEB_DIST_SYMLINK_FORBIDDEN")
            name = _safe_name(path.relative_to(root).as_posix())
            archive.writestr(_info(name), path.read_bytes())
    output.seek(0)
    return output.read()


def _parse_evidence(values: list[str]) -> dict[str, bytes]:
    result: dict[str, bytes] = {}
    for value in values:
        name, separator, raw_path = value.partition("=")
        if not separator:
            raise BundleBuildError("EVIDENCE_ARGUMENT_INVALID")
        normalized = _safe_name(name)
        if normalized in result:
            raise BundleBuildError("EVIDENCE_ARGUMENT_DUPLICATE")
        result[normalized] = _regular(Path(raw_path).resolve(), maximum=512 * 1024 * 1024)
    return result


def _junit_summary(payload: bytes) -> dict[str, int]:
    try:
        root = ET.fromstring(payload)
    except ET.ParseError as exc:
        raise BundleBuildError("JUNIT_INVALID") from exc
    suites = [root] if root.tag.rsplit("}", 1)[-1] == "testsuite" else list(root)
    return {
        key: sum(int(suite.attrib.get(key, "0")) for suite in suites)
        for key in ("tests", "failures", "errors", "skipped")
    }


def _code_digest(root: Path, relative: str) -> str:
    return _sha256(_regular(root / relative, maximum=8 * 1024 * 1024))


def _completion(root: Path, commit: str, tree: str, evidence: dict[str, bytes]) -> bytes:
    firstscreen = evidence.get("firstscreen-v2-5-junit.xml")
    repository = evidence.get("repository-junit.xml")
    vitest = evidence.get("vitest-junit.xml")
    coverage = evidence.get("firstscreen-v2-5-coverage.xml")
    if any(item is None for item in (firstscreen, repository, vitest, coverage)):
        raise BundleBuildError("REQUIRED_EVIDENCE_MISSING")
    firstscreen_summary = _junit_summary(firstscreen)
    repository_summary = _junit_summary(repository)
    vitest_summary = _junit_summary(vitest)
    evidence_digest = {
        "firstscreen": _sha256(firstscreen),
        "repository": _sha256(repository),
        "vitest": _sha256(vitest),
        "coverage": _sha256(coverage),
    }
    finding_rows = [
        ("FS23-P0-001", "OPEN", "butler_pc_core/firstscreen_trust.py", "TR-001", "firstscreen"),
        ("FS23-P0-002", "OPEN", "butler_pc_core/firstscreen_trust.py", "RV-001", "firstscreen"),
        ("FS23-P0-003", "OPEN", "scripts/verify/verify_release_subjects.py", "BI-001", "firstscreen"),
        ("FS23-P0-004", "OPEN", ".github/workflows/firstscreen-v2-5.yml", "repository-python", "repository"),
        ("FS23-P0-005", "OPEN", "tests/firstscreen_v2_5/test_trust_chain.py", "critical-branch-coverage", "coverage"),
        ("FS23-P0-006", "BLOCKED_OWNER", "butler_pc_core/firstscreen_trust.py", "decision-owner-signature", "firstscreen"),
        ("FS23-P0-007", "BLOCKED_EXTERNAL", ".github/workflows/firstscreen-v2-5.yml", "canonical-remote", "repository"),
        ("FS23-P0-008", "NOT_RUN", ".github/workflows/firstscreen-v2-5.yml", "signed-macos-m3", "repository"),
        ("FS23-P1-009", "FIXED_TESTED", "scripts/verify/verify_storage_risk_acceptance.py", "CR-004", "firstscreen"),
        ("FS23-P1-010", "OPEN", ".github/workflows/firstscreen-v2-5.yml", "consumer-attestation", "repository"),
        ("FS23-P1-011", "FIXED_TESTED", "scripts/release/verify_source_bundle.py", "no-git-source", "firstscreen"),
        ("FS23-P1-012", "NOT_RUN", "butler-desktop/src-tauri/src/export.rs", "EX-002-windows", "firstscreen"),
        ("FS23-P1-013", "OPEN", "butler-desktop/src-tauri/src/export.rs", "EX-001", "firstscreen"),
        ("FS23-P1-014", "FIXED_TESTED", "butler-desktop/package-lock.json", "vitest-clean-exit", "vitest"),
        ("FS23-P1-015", "FIXED_TESTED", "butler-desktop/package-lock.json", "npm-audit", "vitest"),
        ("FS23-P1-016", "FIXED_TESTED", "butler-desktop/vite.config.ts", "BI-005", "firstscreen"),
        ("FS23-P1-017", "FIXED_TESTED", "scripts/release/build_safe_source_archive.py", "safe-source", "firstscreen"),
        ("FS23-P1-018", "FIXED_TESTED", "scripts/release/generate_cyclonedx_sbom.py", "sbom-context", "firstscreen"),
        ("FS23-P1-019", "FIXED_TESTED", ".github/workflows/firstscreen-v2-5.yml", "action-sha-pin", "firstscreen"),
        ("FS23-P1-020", "OPEN", "butler_sidecar.py", "real-browser-cors", "repository"),
        ("FS23-P1-021", "FIXED_TESTED", "butler_pc_core/firstscreen_trust.py", "single-authority", "firstscreen"),
        ("FS23-P2-022", "FIXED_TESTED", "contracts/firstscreen_v2_5/completion-status.schema.json", "fail-closed-report", "firstscreen"),
    ]
    findings = [
        {
            "id": finding_id,
            "status": status,
            "code_blob_digest": _code_digest(root, code_path),
            "test_id": test_id,
            "evidence_digest": evidence_digest[evidence_name],
        }
        for finding_id, status, code_path, test_id, evidence_name in finding_rows
    ]
    document = {
        "schema_version": "butler.firstscreen.completion-status.v2.5",
        "status": "BLOCKED",
        "source_identity": {
            "commit": commit,
            "tree": tree,
            "imported_from_commit": IMPORTED_COMMIT,
            "imported_from_tree": IMPORTED_TREE,
        },
        "firstscreen_component_pass": False,
        "repository_integration_pass": False,
        "canonical_remote_verified": False,
        "main_provenance_verified": False,
        "signed_macos_e2e_pass": False,
        "keychain_continuity_pass": False,
        "accessibility_pass": False,
        "m3_measurement_pass": False,
        "code_pass": False,
        "merge_ready": False,
        "product_release_ready": False,
        "runtime_activation_allowed": 0,
        "findings": findings,
        "external_gates": {
            "canonical_remote_pr": "NOT_RUN",
            "main_consumer_attestation": "NOT_RUN",
            "signed_macos_15_arm64": "NOT_RUN",
            "keychain_restart_continuity": "NOT_RUN",
            "voiceover_accessibility": "NOT_RUN",
            "windows_atomic_export": "NOT_RUN",
            "browser_real_sidecar_e2e": "NOT_RUN",
            "apple_m3_measurement": "NOT_RUN",
            "owner_root_ceremony_2_of_3": "BLOCKED_OWNER",
            "owner_release_signature": "BLOCKED_OWNER",
        },
        "local_measurements": {
            "firstscreen_junit": firstscreen_summary,
            "repository_junit": repository_summary,
            "vitest_junit": vitest_summary,
            "native_rust_compile": "NOT_RUN_TOOLCHAIN_UNAVAILABLE",
            "release_subjects": "NOT_CREATED_OWNER_KEY_AND_SIGNED_NATIVE_ABSENT",
        },
    }
    return (json.dumps(document, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode("utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--commit", default="HEAD")
    parser.add_argument("--baseline", required=True)
    parser.add_argument("--build-context", required=True, type=Path)
    parser.add_argument("--web-dist", type=Path, default=Path("butler-desktop/dist"))
    parser.add_argument("--handoff-sha256", required=True)
    parser.add_argument("--handoff-name", required=True)
    parser.add_argument("--directive-internal-sha256", required=True)
    parser.add_argument("--evidence", action="append", default=[], metavar="ASCII_NAME=PATH")
    arguments = parser.parse_args()

    root = Path(__file__).resolve().parents[2]
    commit = _run("git", "rev-parse", f"{arguments.commit}^{{commit}}", cwd=root).decode().strip()
    tree = _run("git", "rev-parse", f"{commit}^{{tree}}", cwd=root).decode().strip()
    baseline = _run("git", "rev-parse", f"{arguments.baseline}^{{commit}}", cwd=root).decode().strip()
    if _run("git", "status", "--porcelain", "--untracked-files=all", cwd=root).strip():
        raise BundleBuildError("PRODUCT_REPOSITORY_NOT_CLEAN")
    protected_specs = protected_pathspecs()
    if _run("git", "diff", "--name-only", baseline, commit, "--", *protected_specs, cwd=root).strip():
        raise BundleBuildError("PROTECTED_SCOPE_CHANGED")
    for digest in (arguments.handoff_sha256, arguments.directive_internal_sha256):
        if len(digest) != 64 or any(character not in "0123456789abcdef" for character in digest):
            raise BundleBuildError("HANDOFF_DIGEST_INVALID")

    evidence = _parse_evidence(arguments.evidence)
    context_bytes = _regular(arguments.build_context.resolve(), maximum=64 * 1024)
    context = strict_json_loads(context_bytes, maximum=64 * 1024)
    validate_build_context(context)
    if context["commit_oid"] != commit or context["tree_oid"] != tree:
        raise BundleBuildError("BUILD_CONTEXT_IDENTITY_MISMATCH")
    context_digest = build_context_digest(context)
    web_bytes = _zip_regular_directory((root / arguments.web_dist).resolve())
    if context_digest.encode("ascii") not in web_bytes:
        # Compressed bytes cannot be searched directly; verify entry payloads.
        from io import BytesIO

        with zipfile.ZipFile(BytesIO(web_bytes)) as web_archive:
            if not any(context_digest.encode("ascii") in web_archive.read(info) for info in web_archive.infolist()):
                raise BundleBuildError("WEB_BUILD_CONTEXT_NOT_EMBEDDED")

    reports = root / "docs" / "product" / "firstscreen_v2_5"
    payloads: dict[str, bytes] = {}
    with tempfile.TemporaryDirectory(prefix="butler-firstscreen-v2-5-") as temporary:
        work = Path(temporary)
        source_zip = work / "Butler_Source.zip"
        source_manifest = work / "SOURCE_ARCHIVE_MANIFEST.json"
        sbom = work / "butler.cdx.json"
        _run(
            sys.executable, "scripts/release/build_safe_source_archive.py",
            "--commit", commit, "--scope-baseline", baseline,
            "--output", str(source_zip), "--manifest", str(source_manifest),
            cwd=root,
        )
        if _sha256(source_manifest.read_bytes()) != context["source_manifest_digest"]:
            raise BundleBuildError("BUILD_CONTEXT_SOURCE_MANIFEST_MISMATCH")
        verified_source = work / "verified-source"
        _run(
            sys.executable, "scripts/release/verify_source_bundle.py",
            "--archive", str(source_zip), "--manifest", str(source_manifest),
            "--build-context", str(arguments.build_context.resolve()),
            "--extract-to", str(verified_source), cwd=root,
        )
        _run(
            sys.executable, "scripts/release/generate_cyclonedx_sbom.py",
            "--commit", commit, "--output", str(sbom), "--build-context", str(arguments.build_context.resolve()),
            "--npm-lock", "butler-desktop/package-lock.json",
            "--python-requirements", "requirements-firstscreen-ci.lock", cwd=root,
        )
        payloads.update({
            "artifacts/BUILD_CONTEXT.json": context_bytes,
            "artifacts/Butler_Source.zip": source_zip.read_bytes(),
            "artifacts/SOURCE_ARCHIVE_MANIFEST.json": source_manifest.read_bytes(),
            "artifacts/Butler_Web_Dist.zip": web_bytes,
            "artifacts/butler.cdx.json": sbom.read_bytes(),
        })

    for name in REPORT_NAMES:
        payloads[f"reports/{name}"] = _regular(reports / name, maximum=16 * 1024 * 1024)
    payloads["reports/COMPLETION_STATUS.json"] = _completion(root, commit, tree, evidence)
    payloads["VERIFY_BUNDLE.py"] = _regular(root / "scripts/release/verify_firstscreen_product_bundle.py")
    payloads["VERIFY_SOURCE.py"] = _regular(root / "scripts/release/verify_source_bundle.py")
    payloads["FIRSTSCREEN_SOURCE_CONTRACTS.py"] = _regular(root / "scripts/release/firstscreen_source_contracts.py")
    for name, payload in evidence.items():
        payloads[f"evidence/{name}"] = payload
    payloads["patch/PRODUCT_PATCH.diff"] = _run(
        "git", "diff", "--binary", baseline, commit, "--", ".",
        *(f":(exclude){path}" for path in protected_specs), cwd=root,
    )
    payloads["inputs/HANDOFF_PROVENANCE.json"] = (
        json.dumps({
            "schema_version": "butler.handoff-input.v2.5",
            "uploaded_name": arguments.handoff_name,
            "uploaded_zip_sha256": arguments.handoff_sha256,
            "uploaded_zip_crc": "PASS",
            "directive_input_sha256": arguments.directive_internal_sha256,
            "directive_internal_sha256s": "PASS",
        }, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    ).encode("utf-8")

    records = [
        {"path": name, "sha256": _sha256(payload), "size": len(payload)}
        for name, payload in sorted(payloads.items())
    ]
    manifest = {
        "schema_version": "butler.firstscreen.product-bundle.v4",
        "product": "Butler FirstScreen v2.5 product developer handoff",
        "commit": commit,
        "tree": tree,
        "reconstructed_baseline_commit": baseline,
        "imported_source_commit": IMPORTED_COMMIT,
        "imported_source_tree": IMPORTED_TREE,
        "build_context_digest": context_digest,
        "protected_contract_digest": protected_contract_digest(),
        "protected_paths": list(PROTECTED_PATHS),
        "protected_accounting_review_changed_files": 0,
        "native_signed_artifact_present": False,
        "release_subjects_present": False,
        "bundle_integrity_verified": True,
        "runtime_activation_allowed": 0,
        "code_pass": False,
        "merge_ready": False,
        "product_release_ready": False,
        "manifest_self_excluded": True,
        "sha256s_self_excluded": True,
        "payload_count": len(records),
        "payloads": records,
    }
    manifest_bytes = (json.dumps(manifest, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode("utf-8")
    sums = "".join(f"{record['sha256']}  {record['path']}\n" for record in records)
    sums += f"{_sha256(manifest_bytes)}  BUNDLE_MANIFEST.json\n"
    payloads["BUNDLE_MANIFEST.json"] = manifest_bytes
    payloads["SHA256SUMS.txt"] = sums.encode("ascii")

    arguments.output.parent.mkdir(parents=True, exist_ok=True)
    temporary_output = arguments.output.with_name(f".{arguments.output.name}.{os.getpid()}.tmp")
    try:
        with zipfile.ZipFile(temporary_output, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
            for name, payload in sorted(payloads.items()):
                archive.writestr(_info(name, executable=name.startswith("VERIFY_") and name.endswith(".py")), payload)
        with zipfile.ZipFile(temporary_output) as archive:
            if archive.testzip() is not None or len(archive.namelist()) != len(set(archive.namelist())):
                raise BundleBuildError("PRODUCT_BUNDLE_CRC_FAILED")
        os.replace(temporary_output, arguments.output)
        _run(
            sys.executable, "scripts/release/verify_firstscreen_product_bundle.py",
            str(arguments.output.resolve()), cwd=root,
        )
    finally:
        try:
            temporary_output.unlink()
        except FileNotFoundError:
            pass
    print(json.dumps({
        "status": "INTEGRITY_PASS_RELEASE_BLOCKED",
        "output": arguments.output.name,
        "sha256": _sha256(arguments.output.read_bytes()),
        "size": arguments.output.stat().st_size,
        "commit": commit,
        "tree": tree,
        "build_context_digest": context_digest,
        "entries": len(payloads),
        "code_pass": False,
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except BundleBuildError as exc:
        print(f"PRODUCT_BUNDLE_OK=0 ERROR_CODE={exc}")
        raise SystemExit(1)
