from __future__ import annotations

import hashlib
import hmac
import json
import os
import stat
import unicodedata
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any

from .errors import PolicyLoadError
from .immutable import FrozenPolicyMap, deep_freeze

POLICY_PROFILE_ID = "atlink.smb.v1"
CHART_RAW_SHA256 = "b80d79bd54a0d4e54d6c9b5abe87d811032b78fd7f072ea5961baf37f221e6a0"
MAPPING_V1_RAW_SHA256 = "14bdaad6a4362b051021f25afa982110868d08f27dbf8b2f57dfc01610f04b14"
DRAFT_MANIFEST_RAW_SHA256 = "8ced1c6ad28c0b4d1f9fd120a2d08f319e65a73de2752d7e916727c8b9edc314"
MAX_DOCUMENT_BYTES = 4 * 1024 * 1024
MAX_DEPTH = 64
MAX_ARRAY_ITEMS = 10_000
MAX_OBJECT_KEYS = 10_000
MAX_STRING_BYTES = 1 * 1024 * 1024
MAX_ARTIFACTS = 64

_SCHEMA_BY_LOGICAL_ID = {
    "CHART_UPSTREAM": "chart_of_accounts.v1.schema.json",
    "MAPPING_V1_UPSTREAM": "account_mapping_rules.v1.schema.json",
    "MAPPING_V2_DRAFT": "account_mapping_rules.v2.schema.json",
    "POSTING_OVERLAY_TEMPLATE": "posting_policy_overlay.v1.schema.json",
    "REPORT_MAPPING_TEMPLATE": "report_mapping.v1.schema.json",
    "VENDOR_REGISTRY_TEMPLATE": "vendor_descriptor_registry.v1.schema.json",
    "TAX_POLICY_TEMPLATE": "tax_policy.v1.schema.json",
    "CASH_FLOW_POLICY_TEMPLATE": "cash_flow_event_policy.v1.schema.json",
    "BINDING_STATUS": "binding_status.v2.1.schema.json",
}


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise PolicyLoadError("POLICY_SCHEMA", "DUPLICATE_JSON_KEY")
        result[key] = value
    return result


def _reject_nonfinite(_value: str) -> None:
    raise PolicyLoadError("POLICY_SCHEMA", "NONFINITE_NUMBER")


def _reject_float(_value: str) -> None:
    raise PolicyLoadError("POLICY_SCHEMA", "FLOAT_IN_POLICY")


def _decode_json(raw: bytes, *, enforce_policy_rules: bool = True) -> Any:
    if len(raw) > MAX_DOCUMENT_BYTES:
        raise PolicyLoadError("POLICY_RESOURCE", "DOCUMENT_TOO_LARGE")
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise PolicyLoadError("POLICY_SCHEMA", "INVALID_UTF8") from exc
    if text.startswith("\ufeff"):
        raise PolicyLoadError("POLICY_SCHEMA", "UTF8_BOM_FORBIDDEN")
    try:
        value = json.loads(
            text,
            object_pairs_hook=_reject_duplicate_keys,
            parse_constant=_reject_nonfinite,
            parse_float=_reject_float,
        )
    except PolicyLoadError:
        raise
    except (json.JSONDecodeError, RecursionError, ValueError) as exc:
        raise PolicyLoadError("POLICY_SCHEMA", "INVALID_JSON") from exc
    _enforce_limits(value)
    if enforce_policy_rules:
        _reject_confusable_identifiers(value)
        _reject_invented_codes(value)
    return value


def _enforce_limits(value: Any, *, depth: int = 0) -> None:
    if depth > MAX_DEPTH:
        raise PolicyLoadError("POLICY_RESOURCE", "MAX_DEPTH_EXCEEDED")
    if isinstance(value, str):
        if len(value.encode("utf-8")) > MAX_STRING_BYTES:
            raise PolicyLoadError("POLICY_RESOURCE", "STRING_TOO_LARGE")
        return
    if isinstance(value, list):
        if len(value) > MAX_ARRAY_ITEMS:
            raise PolicyLoadError("POLICY_RESOURCE", "ARRAY_TOO_LARGE")
        for item in value:
            _enforce_limits(item, depth=depth + 1)
        return
    if isinstance(value, dict):
        if len(value) > MAX_OBJECT_KEYS:
            raise PolicyLoadError("POLICY_RESOURCE", "OBJECT_TOO_LARGE")
        for key, item in value.items():
            if not isinstance(key, str):
                raise PolicyLoadError("POLICY_SCHEMA", "NON_STRING_KEY")
            _enforce_limits(key, depth=depth + 1)
            _enforce_limits(item, depth=depth + 1)


def _reject_confusable_identifiers(value: Any) -> None:
    identifier_keys = {
        "schema_version", "policy_profile_id", "bundle_version", "logical_id",
        "relative_path", "account_id", "parent_account_id", "rule_id", "guard_id",
        "descriptor_id", "approval_id", "tax_policy_id", "cash_flow_policy_id",
    }
    if isinstance(value, dict):
        for key, item in value.items():
            if unicodedata.normalize("NFKC", key) != key:
                raise PolicyLoadError("POLICY_SCHEMA", "CONFUSABLE_IDENTIFIER")
            if key in identifier_keys and isinstance(item, str) and unicodedata.normalize("NFKC", item) != item:
                raise PolicyLoadError("POLICY_SCHEMA", "CONFUSABLE_IDENTIFIER")
            _reject_confusable_identifiers(item)
    elif isinstance(value, list):
        for item in value:
            _reject_confusable_identifiers(item)


def _reject_invented_codes(value: Any) -> None:
    if isinstance(value, dict):
        for key, item in value.items():
            if key == "code" and item is not None:
                raise PolicyLoadError("ACCOUNT_CODE", "FORBIDDEN_INVENTED_CODE")
            _reject_invented_codes(item)
    elif isinstance(value, list):
        for item in value:
            _reject_invented_codes(item)


def _load_schema(name: str) -> Mapping[str, Any]:
    raw = (Path(__file__).with_name("schemas") / name).read_bytes()
    schema = _decode_json(raw, enforce_policy_rules=False)
    if not isinstance(schema, dict):
        raise PolicyLoadError("POLICY_SCHEMA", "INVALID_SCHEMA_DOCUMENT")
    try:
        from jsonschema import Draft202012Validator
    except ImportError as exc:
        raise PolicyLoadError("POLICY_SCHEMA", "VALIDATOR_UNAVAILABLE") from exc
    try:
        Draft202012Validator.check_schema(schema)
    except Exception as exc:
        raise PolicyLoadError("POLICY_SCHEMA", "INVALID_SCHEMA_CONTRACT") from exc
    return schema


def _validate_schema(document: Any, schema_name: str) -> None:
    try:
        from jsonschema import Draft202012Validator, FormatChecker
    except ImportError as exc:
        raise PolicyLoadError("POLICY_SCHEMA", "VALIDATOR_UNAVAILABLE") from exc
    validator = Draft202012Validator(_load_schema(schema_name), format_checker=FormatChecker())
    errors = sorted(validator.iter_errors(document), key=lambda error: tuple(str(item) for item in error.absolute_path))
    if errors:
        detail = "UNKNOWN_KEY" if errors[0].validator in {"additionalProperties", "unevaluatedProperties"} else "INVALID_DOCUMENT"
        raise PolicyLoadError("POLICY_SCHEMA", detail)


def load_policy_document(
    raw: bytes,
    expected_sha256: str,
    *,
    schema_name: str | None = None,
) -> Mapping[str, Any]:
    actual = hashlib.sha256(raw).hexdigest()
    if not hmac.compare_digest(actual, expected_sha256):
        raise PolicyLoadError("POLICY_DIGEST", "SHA256_MISMATCH")
    document = _decode_json(raw)
    if not isinstance(document, dict):
        raise PolicyLoadError("POLICY_SCHEMA", "ROOT_NOT_OBJECT")
    if schema_name is not None:
        _validate_schema(document, schema_name)
    return document


def _safe_parts(relative_path: str) -> tuple[str, ...]:
    if not relative_path or "\x00" in relative_path or "\\" in relative_path:
        raise PolicyLoadError("POLICY_PATH", "UNSAFE_RELATIVE_PATH")
    path = PurePosixPath(relative_path)
    if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        raise PolicyLoadError("POLICY_PATH", "UNSAFE_RELATIVE_PATH")
    return path.parts


def _read_regular_file(root: Path, relative_path: str) -> bytes:
    parts = _safe_parts(relative_path)
    nofollow = getattr(os, "O_NOFOLLOW", 0)
    cloexec = getattr(os, "O_CLOEXEC", 0)
    directory = getattr(os, "O_DIRECTORY", 0)
    root_flags = os.O_RDONLY | directory | nofollow | cloexec
    try:
        current_fd = os.open(root, root_flags)
    except OSError as exc:
        raise PolicyLoadError("POLICY_PATH", "BUNDLE_ROOT_UNSAFE") from exc
    try:
        for part in parts[:-1]:
            try:
                next_fd = os.open(part, os.O_RDONLY | directory | nofollow | cloexec, dir_fd=current_fd)
            except OSError as exc:
                raise PolicyLoadError("POLICY_PATH", "UNSAFE_PATH_COMPONENT") from exc
            os.close(current_fd)
            current_fd = next_fd
        try:
            file_fd = os.open(parts[-1], os.O_RDONLY | nofollow | cloexec, dir_fd=current_fd)
        except OSError as exc:
            raise PolicyLoadError("POLICY_ARTIFACT", "MISSING_OR_UNSAFE") from exc
        try:
            before = os.fstat(file_fd)
            if not stat.S_ISREG(before.st_mode):
                raise PolicyLoadError("POLICY_ARTIFACT", "NOT_REGULAR_FILE")
            if before.st_size > MAX_DOCUMENT_BYTES:
                raise PolicyLoadError("POLICY_RESOURCE", "DOCUMENT_TOO_LARGE")
            chunks: list[bytes] = []
            remaining = MAX_DOCUMENT_BYTES + 1
            while remaining:
                chunk = os.read(file_fd, min(128 * 1024, remaining))
                if not chunk:
                    break
                chunks.append(chunk)
                remaining -= len(chunk)
            raw = b"".join(chunks)
            after = os.fstat(file_fd)
            identity_before = (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns, before.st_ctime_ns)
            identity_after = (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns, after.st_ctime_ns)
            if identity_before != identity_after or len(raw) != before.st_size:
                raise PolicyLoadError("POLICY_ARTIFACT", "CHANGED_DURING_READ")
            if len(raw) > MAX_DOCUMENT_BYTES:
                raise PolicyLoadError("POLICY_RESOURCE", "DOCUMENT_TOO_LARGE")
            return raw
        finally:
            os.close(file_fd)
    finally:
        os.close(current_fd)


@dataclass(frozen=True)
class PolicyBundleSnapshot:
    profile_id: str
    bundle_version: str
    manifest_status: str
    approval_id: str | None
    manifest_raw_sha256: str
    bundle_raw_sha256: str
    documents: FrozenPolicyMap[str, Any]
    account_ids: frozenset[str]
    posting_decisions: FrozenPolicyMap[str, Any]
    journal_auto_post_allowed: bool
    operation_ready: bool

    def require_known_account(self, account_id: str) -> None:
        if account_id not in self.account_ids:
            raise PolicyLoadError("ACCOUNT_UNKNOWN", "NOT_IN_REGISTRY")

    def require_postable(self, account_id: str) -> None:
        self.require_known_account(account_id)
        overlay = self.documents["POSTING_OVERLAY_TEMPLATE"]
        if overlay["status"] != "APPROVED" or not overlay["approval_id"]:
            raise PolicyLoadError("POSTING_NOT_ALLOWED", "OVERLAY_UNVERIFIED")
        decision = self.posting_decisions.get(account_id)
        if not decision or decision["node_kind"] != "POSTING" or decision["posting_allowed"] is not True:
            raise PolicyLoadError("POSTING_NOT_ALLOWED", "ACCOUNT_NOT_POSTABLE")

    def require_activation_allowed(self) -> None:
        if self.manifest_status != "APPROVED" or not self.approval_id or not self.operation_ready:
            raise PolicyLoadError("POLICY_APPROVAL", "PRODUCT_ACTIVATION_BLOCKED")
        if not self.journal_auto_post_allowed:
            raise PolicyLoadError("POSTING_NOT_ALLOWED", "OVERLAY_UNVERIFIED")


def _require_unique(items: list[Mapping[str, Any]], key: str, detail: str) -> None:
    values = [item.get(key) for item in items]
    if None in values or len(values) != len(set(values)):
        raise PolicyLoadError("POLICY_SCHEMA", detail)


def _cross_validate(manifest: Mapping[str, Any], documents: Mapping[str, Mapping[str, Any]]) -> None:
    if manifest["policy_profile_id"] != POLICY_PROFILE_ID:
        raise PolicyLoadError("POLICY_PROFILE", "MISMATCH")
    for document in documents.values():
        profile = document.get("policy_profile_id")
        if profile is not None and profile != POLICY_PROFILE_ID:
            raise PolicyLoadError("POLICY_PROFILE", "MISMATCH")

    chart = documents["CHART_UPSTREAM"]
    mapping_v1 = documents["MAPPING_V1_UPSTREAM"]
    mapping_v2 = documents["MAPPING_V2_DRAFT"]
    overlay = documents["POSTING_OVERLAY_TEMPLATE"]
    binding = documents["BINDING_STATUS"]
    if mapping_v2["bundle_version"] != manifest["bundle_version"]:
        raise PolicyLoadError("POLICY_VERSION", "MIXED_BUNDLE_VERSION")
    if mapping_v1["chart_registry_sha256_ref"] != CHART_RAW_SHA256:
        raise PolicyLoadError("POLICY_DIGEST", "CHART_REFERENCE_MISMATCH")
    if mapping_v2["chart_registry_raw_sha256_ref"] != CHART_RAW_SHA256:
        raise PolicyLoadError("POLICY_DIGEST", "CHART_REFERENCE_MISMATCH")
    if overlay["chart_registry_raw_sha256_ref"] != CHART_RAW_SHA256:
        raise PolicyLoadError("POLICY_DIGEST", "CHART_REFERENCE_MISMATCH")
    if binding["chart_registry_raw_sha256"] != CHART_RAW_SHA256:
        raise PolicyLoadError("POLICY_DIGEST", "CHART_REFERENCE_MISMATCH")
    if binding["mapping_rules_v1_raw_sha256"] != MAPPING_V1_RAW_SHA256:
        raise PolicyLoadError("POLICY_DIGEST", "MAPPING_REFERENCE_MISMATCH")

    accounts = chart["accounts"]
    _require_unique(accounts, "account_id", "DUPLICATE_ACCOUNT_ID")
    _require_unique(accounts, "display_order", "DUPLICATE_DISPLAY_ORDER")
    account_ids = {account["account_id"] for account in accounts}
    accounts_by_id = {account["account_id"]: account for account in accounts}
    for account in accounts:
        parent = account["parent_account_id"]
        if parent is not None and parent not in account_ids:
            raise PolicyLoadError("ACCOUNT_UNKNOWN", "PARENT_NOT_IN_REGISTRY")
        seen: set[str] = set()
        current: str | None = account["account_id"]
        while current is not None:
            if current in seen:
                raise PolicyLoadError("POLICY_SCHEMA", "ACCOUNT_GRAPH_CYCLE")
            seen.add(current)
            current_account = accounts_by_id.get(current)
            current = current_account["parent_account_id"] if current_account else None

    for logical_id in ("MAPPING_V1_UPSTREAM", "MAPPING_V2_DRAFT"):
        rules = documents[logical_id]["rules"]
        _require_unique(rules, "rule_id", "DUPLICATE_RULE_ID")
        for rule in rules:
            target = rule.get("target_account_id")
            if target is not None and target not in account_ids:
                raise PolicyLoadError("ACCOUNT_UNKNOWN", "RULE_TARGET_NOT_IN_REGISTRY")
    priorities = [rule["priority"] for rule in mapping_v2["rules"]]
    if len(priorities) != len(set(priorities)):
        raise PolicyLoadError("POLICY_SCHEMA", "AMBIGUOUS_RULE_PRIORITY")

    decisions = overlay["decisions"]
    _require_unique(decisions, "account_id", "DUPLICATE_POSTING_DECISION")
    if {decision["account_id"] for decision in decisions} != account_ids:
        raise PolicyLoadError("ACCOUNT_UNKNOWN", "OVERLAY_REGISTRY_MISMATCH")

    if manifest["status"] == "APPROVED":
        approval_id = manifest["approval_id"]
        if not approval_id:
            raise PolicyLoadError("POLICY_APPROVAL", "MISSING")
        if mapping_v2["status"] != "APPROVED":
            raise PolicyLoadError("POLICY_APPROVAL", "MAPPING_UNAPPROVED")
        if overlay["status"] != "APPROVED" or overlay["approval_id"] != approval_id:
            raise PolicyLoadError("POLICY_APPROVAL", "OVERLAY_APPROVAL_MISMATCH")
    elif binding["operation_ready"] is True or binding["journal_auto_post_allowed"] is True:
        raise PolicyLoadError("POLICY_APPROVAL", "BLOCKED_BUNDLE_CLAIMS_READY")


def load_policy_bundle(
    bundle_dir: str | os.PathLike[str],
    *,
    expected_manifest_sha256: str,
) -> PolicyBundleSnapshot:
    root = Path(bundle_dir)
    manifest_raw = _read_regular_file(root, "policy_bundle_manifest.v2.1.json")
    manifest = load_policy_document(
        manifest_raw,
        expected_manifest_sha256,
        schema_name="policy_bundle_manifest.v1.schema.json",
    )
    artifacts = manifest["artifacts"]
    if len(artifacts) > MAX_ARTIFACTS:
        raise PolicyLoadError("POLICY_RESOURCE", "TOO_MANY_ARTIFACTS")
    _require_unique(artifacts, "logical_id", "DUPLICATE_LOGICAL_ID")
    _require_unique(artifacts, "relative_path", "DUPLICATE_ARTIFACT_PATH")
    normalized_paths = [unicodedata.normalize("NFKC", item["relative_path"]).casefold() for item in artifacts]
    if len(normalized_paths) != len(set(normalized_paths)):
        raise PolicyLoadError("POLICY_SCHEMA", "DUPLICATE_ARTIFACT_PATH")
    if {item["logical_id"] for item in artifacts} != set(_SCHEMA_BY_LOGICAL_ID):
        raise PolicyLoadError("POLICY_SCHEMA", "ARTIFACT_SET_MISMATCH")

    documents: dict[str, Mapping[str, Any]] = {}
    digest_lines: list[bytes] = []
    for artifact in artifacts:
        logical_id = artifact["logical_id"]
        raw = _read_regular_file(root, artifact["relative_path"])
        if len(raw) != artifact["size"]:
            raise PolicyLoadError("POLICY_DIGEST", "SIZE_MISMATCH")
        document = load_policy_document(
            raw,
            artifact["raw_sha256"],
            schema_name=_SCHEMA_BY_LOGICAL_ID[logical_id],
        )
        documents[logical_id] = document
        digest_lines.append(logical_id.encode("ascii") + b"\0" + artifact["raw_sha256"].encode("ascii"))

    chart_artifact = next(item for item in artifacts if item["logical_id"] == "CHART_UPSTREAM")
    mapping_artifact = next(item for item in artifacts if item["logical_id"] == "MAPPING_V1_UPSTREAM")
    if chart_artifact["raw_sha256"] != CHART_RAW_SHA256 or mapping_artifact["raw_sha256"] != MAPPING_V1_RAW_SHA256:
        raise PolicyLoadError("POLICY_DIGEST", "UPSTREAM_CONTRACT_MISMATCH")
    _cross_validate(manifest, documents)

    frozen_documents = deep_freeze(documents)
    chart = documents["CHART_UPSTREAM"]
    overlay = documents["POSTING_OVERLAY_TEMPLATE"]
    binding = documents["BINDING_STATUS"]
    frozen_decisions = deep_freeze({item["account_id"]: item for item in overlay["decisions"]})
    bundle_digest = hashlib.sha256(b"\n".join(sorted(digest_lines))).hexdigest()
    return PolicyBundleSnapshot(
        profile_id=manifest["policy_profile_id"],
        bundle_version=manifest["bundle_version"],
        manifest_status=manifest["status"],
        approval_id=manifest["approval_id"],
        manifest_raw_sha256=hashlib.sha256(manifest_raw).hexdigest(),
        bundle_raw_sha256=bundle_digest,
        documents=frozen_documents,
        account_ids=frozenset(item["account_id"] for item in chart["accounts"]),
        posting_decisions=frozen_decisions,
        journal_auto_post_allowed=binding["journal_auto_post_allowed"] is True,
        operation_ready=binding["operation_ready"] is True,
    )


def bundled_draft_path() -> Path:
    return Path(__file__).with_name("bundles") / "atlink_smb_v2_1_draft"


def load_bundled_draft() -> PolicyBundleSnapshot:
    return load_policy_bundle(bundled_draft_path(), expected_manifest_sha256=DRAFT_MANIFEST_RAW_SHA256)
