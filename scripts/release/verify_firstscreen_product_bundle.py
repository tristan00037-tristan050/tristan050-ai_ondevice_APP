#!/usr/bin/env python3
"""Independently verify a Butler FirstScreen v2.5 developer handoff bundle."""

from __future__ import annotations

import hashlib
import json
import math
import stat
import sys
import zipfile
from io import BytesIO
from pathlib import Path, PurePosixPath

try:
    from scripts.release.firstscreen_source_contracts import (
        PROTECTED_PATHS,
        SourceContractError,
        protected_contract_digest,
        validate_protected_scope,
    )
except ModuleNotFoundError:  # Standalone product-bundle layout.
    from FIRSTSCREEN_SOURCE_CONTRACTS import (  # type: ignore[no-redef]
        PROTECTED_PATHS,
        SourceContractError,
        protected_contract_digest,
        validate_protected_scope,
    )


MAX_BUNDLE_BYTES = 2 * 1024 * 1024 * 1024
MAX_ENTRY_BYTES = 1024 * 1024 * 1024
MAX_EXPANDED_BYTES = 4 * 1024 * 1024 * 1024
MAX_RATIO = 1000
CONTROL_FILES = {"BUNDLE_MANIFEST.json", "SHA256SUMS.txt"}


class ProductBundleVerificationError(RuntimeError):
    pass


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _safe_name(raw: object, *, ascii_only: bool = True) -> str:
    if not isinstance(raw, str) or "\\" in raw or "\0" in raw:
        raise ProductBundleVerificationError("PATH_INVALID")
    path = PurePosixPath(raw)
    if path.is_absolute() or not path.parts or ".." in path.parts or path.as_posix() != raw:
        raise ProductBundleVerificationError("PATH_INVALID")
    if ascii_only:
        try:
            raw.encode("ascii")
        except UnicodeEncodeError as exc:
            raise ProductBundleVerificationError("PATH_NOT_ASCII") from exc
    return raw


def _reject_constant(_raw: str) -> object:
    raise ProductBundleVerificationError("JSON_NUMBER_INVALID")


def _reject_float(_raw: str) -> object:
    raise ProductBundleVerificationError("JSON_NUMBER_INVALID")


def _pairs(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ProductBundleVerificationError("JSON_DUPLICATE_KEY")
        result[key] = value
    return result


def _document(payload: bytes) -> dict[str, object]:
    try:
        text = payload.decode("utf-8", errors="strict")
        if text.startswith("\ufeff"):
            raise ProductBundleVerificationError("JSON_BOM")
        value = json.loads(
            text,
            object_pairs_hook=_pairs,
            parse_float=_reject_float,
            parse_constant=_reject_constant,
        )
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise ProductBundleVerificationError("JSON_INVALID") from exc
    if not isinstance(value, dict):
        raise ProductBundleVerificationError("JSON_INVALID")
    return value


def _canonical(value: object) -> bytes:
    def encode(item: object) -> str:
        if item is None or isinstance(item, bool):
            return json.dumps(item, separators=(",", ":"))
        if isinstance(item, int) and not isinstance(item, bool):
            return str(item)
        if isinstance(item, float):
            if not math.isfinite(item):
                raise ProductBundleVerificationError("CANONICAL_NUMBER_INVALID")
            raise ProductBundleVerificationError("CANONICAL_FLOAT_FORBIDDEN")
        if isinstance(item, str):
            return json.dumps(item, ensure_ascii=False, separators=(",", ":"))
        if isinstance(item, list):
            return "[" + ",".join(encode(child) for child in item) + "]"
        if isinstance(item, dict) and all(isinstance(key, str) for key in item):
            return "{" + ",".join(
                json.dumps(key, ensure_ascii=False) + ":" + encode(item[key]) for key in sorted(item)
            ) + "}"
        raise ProductBundleVerificationError("CANONICAL_TYPE_INVALID")

    return encode(value).encode("utf-8")


def _read_zip(
    payload: bytes,
    *,
    maximum_entries: int,
    maximum_expanded: int,
    ascii_paths: bool = True,
) -> dict[str, bytes]:
    try:
        archive = zipfile.ZipFile(BytesIO(payload))
    except (OSError, zipfile.BadZipFile) as exc:
        raise ProductBundleVerificationError("NESTED_ZIP_INVALID") from exc
    with archive:
        infos = archive.infolist()
        if not 0 < len(infos) <= maximum_entries:
            raise ProductBundleVerificationError("NESTED_ENTRY_COUNT_INVALID")
        names = [_safe_name(info.filename, ascii_only=ascii_paths) for info in infos]
        if len(names) != len(set(names)):
            raise ProductBundleVerificationError("NESTED_DUPLICATE_ENTRY")
        expanded = 0
        result: dict[str, bytes] = {}
        for info in infos:
            file_type = (info.external_attr >> 16) & 0o170000
            mode = (info.external_attr >> 16) & 0o777
            if file_type != stat.S_IFREG or mode not in {0o600, 0o644, 0o755} or info.flag_bits & 0x1:
                raise ProductBundleVerificationError("NESTED_ENTRY_TYPE_INVALID")
            if info.file_size < 0 or info.file_size > MAX_ENTRY_BYTES:
                raise ProductBundleVerificationError("NESTED_ENTRY_SIZE_INVALID")
            expanded += info.file_size
            if expanded > maximum_expanded:
                raise ProductBundleVerificationError("NESTED_EXPANDED_SIZE_INVALID")
            if info.file_size and (not info.compress_size or info.file_size / info.compress_size > MAX_RATIO):
                raise ProductBundleVerificationError("NESTED_COMPRESSION_RATIO_INVALID")
            result[info.filename] = archive.read(info)
        if archive.testzip() is not None:
            raise ProductBundleVerificationError("NESTED_CRC_INVALID")
        return result


def verify_product_bundle(path: Path) -> None:
    metadata = path.lstat()
    if path.is_symlink() or not stat.S_ISREG(metadata.st_mode) or metadata.st_size > MAX_BUNDLE_BYTES:
        raise ProductBundleVerificationError("BUNDLE_TYPE_INVALID")
    payloads = _read_zip(path.read_bytes(), maximum_entries=1000, maximum_expanded=MAX_EXPANDED_BYTES)
    manifest_bytes = payloads.get("BUNDLE_MANIFEST.json")
    sums_bytes = payloads.get("SHA256SUMS.txt")
    if manifest_bytes is None or sums_bytes is None:
        raise ProductBundleVerificationError("CONTROL_FILE_MISSING")
    manifest = _document(manifest_bytes)
    if manifest.get("schema_version") != "butler.firstscreen.product-bundle.v4":
        raise ProductBundleVerificationError("MANIFEST_SCHEMA_INVALID")
    records = manifest.get("payloads")
    if not isinstance(records, list) or manifest.get("payload_count") != len(records):
        raise ProductBundleVerificationError("PAYLOAD_COUNT_INVALID")
    expected: dict[str, tuple[str, int]] = {}
    ordered_paths: list[str] = []
    for record in records:
        if not isinstance(record, dict):
            raise ProductBundleVerificationError("PAYLOAD_RECORD_INVALID")
        name = _safe_name(record.get("path"))
        digest = record.get("sha256")
        size = record.get("size")
        if (
            not isinstance(digest, str)
            or len(digest) != 64
            or any(character not in "0123456789abcdef" for character in digest)
            or not isinstance(size, int)
            or size < 0
            or name in expected
        ):
            raise ProductBundleVerificationError("PAYLOAD_RECORD_INVALID")
        expected[name] = (digest, size)
        ordered_paths.append(name)
    if ordered_paths != sorted(ordered_paths) or set(payloads) != set(expected) | CONTROL_FILES:
        raise ProductBundleVerificationError("PAYLOAD_SET_INVALID")
    for name, (digest, size) in expected.items():
        payload = payloads[name]
        if len(payload) != size or _sha256(payload) != digest:
            raise ProductBundleVerificationError("PAYLOAD_DIGEST_INVALID")
    expected_sums = "".join(f"{expected[name][0]}  {name}\n" for name in sorted(expected))
    expected_sums += f"{_sha256(manifest_bytes)}  BUNDLE_MANIFEST.json\n"
    if sums_bytes != expected_sums.encode("ascii"):
        raise ProductBundleVerificationError("SHA256SUMS_INVALID")

    if any(manifest.get(key) is not False for key in (
        "native_signed_artifact_present", "release_subjects_present", "code_pass", "merge_ready", "product_release_ready",
    )) or manifest.get("runtime_activation_allowed") != 0:
        raise ProductBundleVerificationError("RELEASE_GATE_STATE_INVALID")
    if (
        manifest.get("protected_paths") != list(PROTECTED_PATHS)
        or manifest.get("protected_contract_digest") != protected_contract_digest()
        or manifest.get("protected_accounting_review_changed_files") != 0
    ):
        raise ProductBundleVerificationError("PROTECTED_CONTRACT_INVALID")

    commit = manifest.get("commit")
    tree = manifest.get("tree")
    context_bytes = payloads.get("artifacts/BUILD_CONTEXT.json")
    source_manifest_bytes = payloads.get("artifacts/SOURCE_ARCHIVE_MANIFEST.json")
    source_zip_bytes = payloads.get("artifacts/Butler_Source.zip")
    web_zip_bytes = payloads.get("artifacts/Butler_Web_Dist.zip")
    sbom_bytes = payloads.get("artifacts/butler.cdx.json")
    completion_bytes = payloads.get("reports/COMPLETION_STATUS.json")
    attack_bytes = payloads.get("reports/ATTACK_MATRIX.json")
    if any(value is None for value in (
        context_bytes, source_manifest_bytes, source_zip_bytes, web_zip_bytes, sbom_bytes, completion_bytes, attack_bytes,
    )):
        raise ProductBundleVerificationError("BOUND_ARTIFACT_MISSING")

    context = _document(context_bytes)
    context_digest = _sha256(_canonical(context))
    if (
        context.get("schema_version") != "butler.firstscreen.build-context.v1"
        or context.get("mode") != "production"
        or context.get("commit_oid") != commit
        or context.get("tree_oid") != tree
        or manifest.get("build_context_digest") != context_digest
    ):
        raise ProductBundleVerificationError("BUILD_CONTEXT_MISMATCH")

    source_manifest = _document(source_manifest_bytes)
    if (
        source_manifest.get("commit") != commit
        or source_manifest.get("tree") != tree
        or context.get("source_manifest_digest") != _sha256(source_manifest_bytes)
    ):
        raise ProductBundleVerificationError("SOURCE_IDENTITY_MISMATCH")
    source_payloads = _read_zip(
        source_zip_bytes,
        maximum_entries=10000,
        maximum_expanded=MAX_EXPANDED_BYTES,
        ascii_paths=False,
    )
    if source_payloads.get("SOURCE_ARCHIVE_MANIFEST.json") != source_manifest_bytes:
        raise ProductBundleVerificationError("NESTED_MANIFEST_MISMATCH")
    source_records = source_manifest.get("files")
    if not isinstance(source_records, list):
        raise ProductBundleVerificationError("SOURCE_RECORDS_INVALID")
    try:
        validate_protected_scope(
            source_manifest.get("protected_scope"),
            target_commit=commit,
            manifest_files=source_records,
        )
    except SourceContractError as exc:
        raise ProductBundleVerificationError("PROTECTED_SCOPE_INVALID") from exc
    for record in source_records:
        if not isinstance(record, dict):
            raise ProductBundleVerificationError("SOURCE_RECORDS_INVALID")
        name = "source/" + _safe_name(record.get("path"), ascii_only=False)
        payload = source_payloads.get(name)
        if payload is None or len(payload) != record.get("size") or _sha256(payload) != record.get("sha256"):
            raise ProductBundleVerificationError("NESTED_SOURCE_PAYLOAD_MISMATCH")

    web_payloads = _read_zip(web_zip_bytes, maximum_entries=10000, maximum_expanded=MAX_EXPANDED_BYTES)
    if not any(context_digest.encode("ascii") in payload for payload in web_payloads.values()):
        raise ProductBundleVerificationError("WEB_CONTEXT_MISMATCH")

    sbom = _document(sbom_bytes)
    properties = {
        item.get("name"): item.get("value")
        for item in sbom.get("metadata", {}).get("component", {}).get("properties", [])
        if isinstance(item, dict)
    }
    if (
        properties.get("butler:git_commit_oid") != commit
        or properties.get("butler:git_tree_oid") != tree
        or properties.get("butler:build_context_digest") != context_digest
    ):
        raise ProductBundleVerificationError("SBOM_IDENTITY_MISMATCH")

    completion = _document(completion_bytes)
    source_identity = completion.get("source_identity", {})
    if (
        completion.get("schema_version") != "butler.firstscreen.completion-status.v2.5"
        or completion.get("status") != "BLOCKED"
        or not isinstance(source_identity, dict)
        or source_identity.get("commit") != commit
        or source_identity.get("tree") != tree
        or completion.get("runtime_activation_allowed") != 0
        or any(completion.get(key) is not False for key in (
            "firstscreen_component_pass", "repository_integration_pass", "canonical_remote_verified",
            "main_provenance_verified", "signed_macos_e2e_pass", "keychain_continuity_pass",
            "accessibility_pass", "m3_measurement_pass", "code_pass", "merge_ready", "product_release_ready",
        ))
    ):
        raise ProductBundleVerificationError("COMPLETION_STATE_INVALID")
    findings = completion.get("findings")
    if not isinstance(findings, list) or len(findings) != 22 or len({item.get("id") for item in findings if isinstance(item, dict)}) != 22:
        raise ProductBundleVerificationError("FINDINGS_CARDINALITY_INVALID")

    attack = _document(attack_bytes)
    scenarios = attack.get("scenarios")
    if (
        attack.get("schema_version") != "butler.firstscreen.attack-matrix.v2.5"
        or not isinstance(scenarios, list)
        or len(scenarios) != 56
        or len({item.get("id") for item in scenarios if isinstance(item, dict)}) != 56
    ):
        raise ProductBundleVerificationError("ATTACK_MATRIX_INVALID")


def main() -> int:
    if len(sys.argv) != 2:
        print("PRODUCT_BUNDLE_INTEGRITY_OK=0 ERROR_CODE=PRODUCT_BUNDLE_INVALID")
        return 2
    try:
        verify_product_bundle(Path(sys.argv[1]).resolve())
    except Exception:
        print("PRODUCT_BUNDLE_INTEGRITY_OK=0 ERROR_CODE=PRODUCT_BUNDLE_INVALID")
        return 1
    print("PRODUCT_BUNDLE_INTEGRITY_OK=1 CODE_PASS=0 RELEASE_READY=0")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
