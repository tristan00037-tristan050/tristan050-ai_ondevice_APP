"""Product orchestration and transactional evidence export for Box5 A4 v3.1."""

from __future__ import annotations

import hashlib
import os
import secrets
import shutil
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Mapping, Protocol

from jsonschema import Draft202012Validator, FormatChecker
from jsonschema.exceptions import SchemaError, ValidationError
from butler_pc_core.build_info import build_info

from .reconciliation_v2 import (
    A4ContractError,
    AdapterContract,
    CompileReceipt,
    MatchResult,
    RunBinding,
    TrustPolicy,
    closed_world_dlp,
    compile_dataframe,
    digest_object,
    jcs_bytes,
    reconcile,
    sha256_bytes,
    strict_json_loads,
    tenant_uuid,
    verify_signed_policy,
)
from .verifier_authority import request_authority_verification


EVIDENCE_FILES = frozenset(
    {
        "run_request.json",
        "input_receipt.json",
        "policy_receipt.json",
        "account_snapshot_receipt.json",
        "graph_observation.json",
        "classification_receipt.json",
        "runtime_invariants.json",
        "dlp_receipt.json",
        "manifest.json",
        "SHA256SUMS",
    }
)
SCHEMA_DIGEST = hashlib.sha256(b"butler.box5.a4.contracts.v3.1").hexdigest()
PINNED_TRUST_POLICY_PATH = (
    Path(__file__).resolve().parent
    / "contracts"
    / "a4_v2"
    / "trust_policy.production.json"
)
EVIDENCE_SCHEMA_PATH = (
    Path(__file__).resolve().parent
    / "contracts"
    / "a4_v2"
    / "evidence_bundle.schema.json"
)
CODE_DICTIONARY_PATH = (
    Path(__file__).resolve().parent
    / "contracts"
    / "a4_v31"
    / "code_dictionary.production.json"
)
VERIFICATION_RECEIPT_SCHEMA_PATH = (
    Path(__file__).resolve().parent
    / "contracts"
    / "a4_v31"
    / "verification_receipt.schema.json"
)
VERIFIER_AUTHORITY_TRUST_PATH = (
    Path(__file__).resolve().parent
    / "contracts"
    / "a4_v31"
    / "verifier_authority_trust.production.json"
)
ALLOW_TEST_VERIFIER_AUTHORITY = False
VERIFIER_TOKEN_KEY_FIELDS = frozenset(
    {
        "schema_version",
        "tenant_id",
        "key_id",
        "own_account_key_b64",
        "bank_reference_key_b64",
        "counterparty_account_key_b64",
        "run_transaction_key_b64",
    }
)
CODE_CLOSURE_FILES = (
    "butler_pc_core/a4_verifier/cli.py",
    "butler_pc_core/a4_verifier/canonical.py",
    "butler_pc_core/a4_verifier/contracts.py",
    "butler_pc_core/a4_verifier/errors.py",
    "butler_pc_core/a4_verifier/receipt.py",
    "butler_pc_core/accounting/assignment/a4_store_schema_v32.py",
    "butler_pc_core/accounting/classify/reconciliation_v2.py",
    "butler_pc_core/accounting/classify/reconciliation_service_v2.py",
    "butler_pc_core/accounting/classify/source_snapshot_v2_1.py",
    "butler_pc_core/accounting/classify/verifier_authority.py",
    "butler_pc_core/accounting/classify/contracts/a4_v2/evidence_bundle.schema.json",
    "butler_pc_core/accounting/classify/contracts/a4_v31/code_dictionary.production.json",
    "butler_pc_core/accounting/classify/contracts/a4_v31/release_manifest.production.json",
    "butler_pc_core/accounting/classify/contracts/a4_v31/verifier_authority_trust.production.json",
    "butler_pc_core/accounting/classify/contracts/a4_v31/verifier_authority_trust.schema.json",
    "butler_pc_core/accounting/classify/contracts/a4_v31/verification_receipt.schema.json",
)


class ReconciliationProductStore(Protocol):
    def resolve_account_identity(
        self, tenant_id: str, lookup_key_id: str, lookup_token: str
    ) -> str: ...
    def a4_own_account_registry(self, tenant_id: str) -> dict[str, Any]: ...
    def queue_reconciliation_run(self, **kwargs: Any) -> Any: ...
    def claim_reconciliation_run(self, **kwargs: Any) -> int: ...
    def commit_reconciliation_run(self, **kwargs: Any) -> Any: ...
    def reconciliation_payloads(
        self, tenant_id: str, run_id: str
    ) -> dict[str, bytes]: ...
    def mark_reconciliation_exported(self, tenant_id: str, run_id: str) -> None: ...
    def mark_reconciliation_verified(
        self, tenant_id: str, run_id: str, receipt: dict[str, Any]
    ) -> None: ...


def queue_canonical_product_reconciliation(
    *,
    store: ReconciliationProductStore,
    owner_request: Mapping[str, Any],
    observed_at: datetime,
) -> dict[str, Any]:
    """Persist the A4 request before the caller is allowed to schedule a worker."""

    created_at = observed_at.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    nonce = str(owner_request.get("nonce", ""))
    queue_record = {
        "tenant_id": str(owner_request.get("tenant_id", "")),
        "run_id": str(owner_request.get("run_id", "")),
        "nonce": nonce,
        "nonce_digest": sha256_bytes(bytes.fromhex(nonce)),
        "idempotency_digest": digest_object(
            {
                "tenant_id": owner_request.get("tenant_id"),
                "run_id": owner_request.get("run_id"),
                "input_closure_digest": owner_request.get("input_closure_digest"),
            }
        ),
        "code_tree_oid": str(owner_request.get("code_tree_oid", "")),
        "input_closure_digest": str(owner_request.get("input_closure_digest", "")),
        "created_at": created_at,
    }
    result = store.queue_reconciliation_run(run=queue_record)
    return dict(getattr(result, "response", result))


def approved_split_adapter() -> AdapterContract:
    """Current approved Korean split debit/credit adapter contract."""

    return AdapterContract(
        adapter_id="BUTLER_KR_BANK_SPLIT_V2",
        schema_version="2.0.0",
        zone_name="Asia/Seoul",
        source_account="명세계좌번호",
        bank_code="명세은행코드",
        booking_date="거래일자",
        withdrawal="출금",
        deposit="입금",
        reference="거래참조번호",
        counter_account="상대계좌번호",
        fee_type="거래유형",
        product_code="상품코드",
        channel="거래채널",
        currency="통화",
        value_date="가치일자",
        duplicate_of_reference="중복원거래참조번호",
        reversal_of_reference="취소원거래참조번호",
        allowed_date_formats=("%Y-%m-%d", "%Y%m%d"),
    )


def load_trust_policy(path: Path) -> TrustPolicy:
    if not path.is_file() or path.is_symlink():
        raise A4ContractError("BLOCK_UNPINNED_KEY")
    payload = strict_json_loads(path.read_bytes())
    required = {
        "schema_version",
        "enabled",
        "policy_type",
        "algorithm",
        "expected_signer_key_id",
        "public_key_b64",
        "revocation_epoch",
    }
    if not isinstance(payload, dict) or set(payload) != required:
        raise A4ContractError("BLOCK_UNPINNED_KEY")
    if (
        payload["schema_version"] != "1.0.0"
        or payload["enabled"] is not True
        or payload["policy_type"] != "A4_RECON_POLICY"
    ):
        raise A4ContractError("BLOCK_UNPINNED_KEY")
    if type(payload["revocation_epoch"]) is not int or payload["revocation_epoch"] < 0:
        raise A4ContractError("BLOCK_UNPINNED_KEY")
    trust = TrustPolicy(
        str(payload["expected_signer_key_id"]),
        str(payload["public_key_b64"]),
        payload["revocation_epoch"],
        (str(payload["policy_type"]), "A4_FEE_SCHEDULE"),
        str(payload["algorithm"]),
    )
    trust.public_key()
    return trust


def source_identity(path: Path) -> tuple[str, int]:
    """Owner-side physical input identity, calculated before producer import."""

    if not path.is_file() or path.is_symlink():
        raise A4ContractError("BLOCK_INPUT_CLOSURE")
    size = path.stat().st_size
    if size <= 0 or size > 512 * 1024 * 1024:
        raise A4ContractError("BLOCK_RESOURCE_LIMIT")
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while block := handle.read(1024 * 1024):
            digest.update(block)
    return digest.hexdigest(), size


def make_owner_request(
    *,
    run_id: str,
    profile_id: str,
    code_tree_oid: str,
    source_digest: str,
    source_size: int,
) -> dict[str, Any]:
    """Construct immutable owner data before importing the producer service."""

    try:
        canonical_run = str(uuid.UUID(run_id))
    except (ValueError, TypeError) as exc:
        raise A4ContractError("BLOCK_RUN_BINDING") from exc
    nonce = secrets.token_hex(32)
    return {
        "run_id": canonical_run,
        "nonce": nonce,
        "tenant_id": tenant_uuid(profile_id),
        "code_tree_oid": code_tree_oid,
        "source_file_sha256": source_digest,
        "source_file_size": source_size,
        "input_closure_digest": digest_object(
            {"source_file_sha256": source_digest, "source_file_size": source_size}
        ),
    }


def _classification_payload(run_id: str, result: MatchResult) -> dict[str, Any]:
    forced = [edge.safe_dict() for edge in result.forced_edges]
    payload = {
        "schema_version": "2.0.0",
        "run_id": run_id,
        "forced_edges": forced,
        "components": [component.safe_dict(run_id) for component in result.components],
        "globally_unmatched_txn_uids": list(result.globally_unmatched_txn_uids),
        "shadow_only": True,
        "affects_reporting": False,
    }
    if result.terminal_groups:
        payload["terminal_groups"] = [
            group.safe_dict() for group in result.terminal_groups
        ]
    return payload


def _build_evidence(
    *,
    binding: RunBinding,
    compilation: CompileReceipt,
    adapter: AdapterContract,
    policy_document: Mapping[str, Any],
    result: MatchResult,
    row_manifest: Mapping[str, Any],
    snapshot_receipt: Mapping[str, Any] | None,
) -> dict[str, bytes]:
    policy_receipt = policy_document["receipt"]
    base: dict[str, Any] = {
        "run_request.json": binding.safe_dict(),
        "input_receipt.json": {
            "schema_version": "2.0.0",
            "run_id": binding.run_id,
            "nonce_digest": binding.nonce_digest,
            "tenant_id": binding.tenant_id,
            "source_file_sha256": compilation.source_file_sha256,
            "source_file_size": compilation.source_file_size,
            "source_row_count": compilation.source_row_count,
            "input_closure_digest": binding.input_closure_digest,
            "adapter_digest": compilation.adapter_digest,
            "dictionary_digest": compilation.dictionary_digest,
            "registry_digest": compilation.registry_digest,
            "adapter_contract": adapter.safe_dict(),
            "source_snapshot_receipt": snapshot_receipt,
            "row_closure": row_manifest,
            "compiled_transactions": [
                item.safe_dict() for item in compilation.transactions
            ],
        },
        "policy_receipt.json": policy_receipt,
        "account_snapshot_receipt.json": {
            "schema_version": "2.0.0",
            "run_id": binding.run_id,
            "nonce_digest": binding.nonce_digest,
            "tenant_id": binding.tenant_id,
            "account_snapshot_digest": compilation.account_snapshot_digest,
            "registry_digest": compilation.registry_digest,
            "lookup_key_ids": list(compilation.lookup_key_ids),
            "accounts": list(compilation.account_continuity),
        },
        "graph_observation.json": {
            "schema_version": "2.1.0",
            "run_id": binding.run_id,
            "nonce_digest": binding.nonce_digest,
            "tenant_id": binding.tenant_id,
            "objective": [
                "MAX_MATCHED_PRINCIPALS",
                "MIN_TIME_DISTANCE",
                "MIN_FEE_PENALTY",
                "ORDERED_EDGE_ID_VECTOR",
            ],
            "policy_payload": policy_document["payload"],
            "candidate_pair_checks": result.candidate_pair_checks,
            "max_candidate_bucket_size": result.max_candidate_bucket_size,
            "candidate_subset_branches": result.candidate_subset_branches,
            "edges": [edge.safe_dict() for edge in result.edges],
        },
        "classification_receipt.json": _classification_payload(binding.run_id, result),
        "runtime_invariants.json": {
            "run_id": binding.run_id,
            "nonce_digest": binding.nonce_digest,
            "shadow_only": True,
            "product_mutation_count": 0,
            "journal_auto_post_allowed": False,
            "affects_reporting": False,
            "runtime_activation_allowed": False,
            "observer_product_bytes_equal": True,
            "terminal_count": 1,
        },
    }
    dlp = closed_world_dlp(base)
    base["dlp_receipt.json"] = {
        "run_id": binding.run_id,
        "nonce_digest": binding.nonce_digest,
        **dlp,
    }
    encoded = {name: jcs_bytes(payload) for name, payload in base.items()}
    manifest = {
        "schema_version": "1.0.0",
        "run_id": binding.run_id,
        "nonce_digest": binding.nonce_digest,
        "code_tree_oid": binding.code_tree_oid,
        "files": [
            {"path": name, "sha256": sha256_bytes(payload), "size": len(payload)}
            for name, payload in sorted(encoded.items())
        ],
    }
    encoded["manifest.json"] = jcs_bytes(manifest)
    schema = strict_json_loads(EVIDENCE_SCHEMA_PATH.read_bytes())
    try:
        Draft202012Validator.check_schema(schema)
        Draft202012Validator(schema, format_checker=FormatChecker()).validate(
            {
                name.removesuffix(".json"): payload
                for name, payload in {**base, "manifest.json": manifest}.items()
            }
        )
    except Exception as exc:
        raise A4ContractError("BLOCK_SCHEMA") from exc
    checksum_lines = [
        f"{sha256_bytes(payload)}  {name}\n".encode("ascii")
        for name, payload in sorted(encoded.items())
    ]
    encoded["SHA256SUMS"] = b"".join(checksum_lines)
    if set(encoded) != EVIDENCE_FILES:
        raise A4ContractError("BLOCK_FILE_SET")
    return encoded


def _classifications(result: MatchResult) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    forced = {edge.edge_id for edge in result.forced_edges}
    for edge in result.edges:
        kind = "FORCED" if edge.edge_id in forced else "AMBIGUOUS"
        records.append(
            {
                "classification_id": edge.edge_id,
                "kind": kind,
                "payload_digest": digest_object(
                    {"edge_id": edge.edge_id, "kind": kind}
                ),
            }
        )
    for txn_uid in result.globally_unmatched_txn_uids:
        records.append(
            {
                "classification_id": digest_object({"unmatched": txn_uid}),
                "kind": "UNMATCHED",
                "payload_digest": digest_object(
                    {"txn_uid": txn_uid, "kind": "UNMATCHED"}
                ),
            }
        )
    for group in result.terminal_groups:
        payload = group.safe_dict()
        records.append(
            {
                "classification_id": group.group_id,
                "kind": "BLOCKED",
                "payload_digest": digest_object(payload),
            }
        )
    return records


def export_from_outbox(
    *,
    store: ReconciliationProductStore,
    tenant_id: str,
    run_id: str,
    evidence_root: Path,
) -> Path:
    """Regenerate the exact file replica from DB-authoritative bytes."""

    payloads = store.reconciliation_payloads(tenant_id, run_id)
    if set(payloads) != EVIDENCE_FILES:
        raise A4ContractError("BLOCK_FILE_SET")
    evidence_root.mkdir(parents=True, exist_ok=True, mode=0o700)
    if evidence_root.is_symlink():
        raise A4ContractError("BLOCK_PATH")
    final = evidence_root / run_id
    if final.exists():
        if final.is_symlink() or not final.is_dir():
            raise A4ContractError("BLOCK_FILE_TYPE")
        names = {item.name for item in final.iterdir()}
        exact = names == set(payloads) and all(
            item.is_file()
            and not item.is_symlink()
            and item.read_bytes() == payloads[item.name]
            for item in final.iterdir()
        )
        if exact:
            store.mark_reconciliation_exported(tenant_id, run_id)
            return final
        quarantine = evidence_root / f"quarantine-{run_id}-{secrets.token_hex(8)}"
        os.replace(final, quarantine)
        raise A4ContractError("BLOCK_IDEMPOTENCY_CONFLICT")
    staging = evidence_root / f".{run_id}.{secrets.token_hex(12)}.staging"
    staging.mkdir(mode=0o700)
    try:
        for name, payload in sorted(payloads.items()):
            if Path(name).name != name:
                raise A4ContractError("BLOCK_PATH")
            target = staging / name
            descriptor = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(descriptor, "wb") as handle:
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
        directory = os.open(staging, os.O_RDONLY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
        os.replace(staging, final)
        parent = os.open(evidence_root, os.O_RDONLY)
        try:
            os.fsync(parent)
        finally:
            os.close(parent)
        store.mark_reconciliation_exported(tenant_id, run_id)
        return final
    except Exception:
        if staging.exists():
            shutil.rmtree(staging, ignore_errors=True)
        raise


def verify_in_separate_process(
    *,
    evidence_dir: Path,
    trust_policy_path: Path,
    token_service: Any,
    tenant_id: str,
    source_fd: int,
    source_suffix: str,
    timeout_seconds: int = 30,
) -> dict[str, Any]:
    resources_root = Path(__file__).resolve().parents[3]
    closure_files: dict[str, str] = {}
    for relative in CODE_CLOSURE_FILES:
        target = resources_root / relative
        if not target.is_file() or target.is_symlink():
            raise A4ContractError("BLOCK_CODE_CLOSURE")
        closure_files[relative] = sha256_bytes(target.read_bytes())
    expected_code_closure_digest = digest_object(closure_files)
    stamp = build_info()
    if stamp.get("source") == "bundled_stamp":
        stamped_closure = stamp.get("a4_code_closure")
        if (
            not isinstance(stamped_closure, dict)
            or stamped_closure.get("files") != closure_files
            or stamped_closure.get("digest") != expected_code_closure_digest
        ):
            raise A4ContractError("BLOCK_CODE_CLOSURE")
    if source_suffix not in {".csv", ".xls", ".xlsx"}:
        raise A4ContractError("BLOCK_UNSUPPORTED_SOURCE_FORMAT")
    material = token_service.a4_verifier_material(tenant_id)
    if (
        not isinstance(material, Mapping)
        or "verification_signing_seed_b64" in material
        or set(material) != VERIFIER_TOKEN_KEY_FIELDS
    ):
        raise A4ContractError("BLOCK_TRUST_UNAVAILABLE")
    material = dict(material)
    try:
        evidence_files = {
            name: (evidence_dir / name).read_bytes() for name in EVIDENCE_FILES
        }
        finance_trust = trust_policy_path.read_bytes()
        dictionary = CODE_DICTIONARY_PATH.read_bytes()
    except OSError as exc:
        raise A4ContractError("BLOCK_INPUT_CLOSURE") from exc
    full_receipt = request_authority_verification(
        authority_trust_path=VERIFIER_AUTHORITY_TRUST_PATH,
        evidence_files=evidence_files,
        finance_trust=finance_trust,
        dictionary=dictionary,
        key_material=material,
        tenant_id=tenant_id,
        source_fd=source_fd,
        source_suffix=source_suffix,
        now=datetime.now(timezone.utc),
        allow_test_authority=ALLOW_TEST_VERIFIER_AUTHORITY,
        timeout_seconds=timeout_seconds,
    )
    try:
        receipt_schema = strict_json_loads(
            VERIFICATION_RECEIPT_SCHEMA_PATH.read_bytes()
        )
        Draft202012Validator.check_schema(receipt_schema)
        Draft202012Validator(
            receipt_schema, format_checker=FormatChecker()
        ).validate(full_receipt)
        run_document = strict_json_loads((evidence_dir / "run_request.json").read_bytes())
        input_document = strict_json_loads((evidence_dir / "input_receipt.json").read_bytes())
        graph_document = strict_json_loads((evidence_dir / "graph_observation.json").read_bytes())
        required_receipt = {
            "schema_version", "contract_id", "run_id", "nonce", "decision",
            "reason_codes", "source_sha256", "ordered_row_root",
            "compiled_manifest_digest", "graph_digest", "evidence_manifest_digest",
            "policy_digest", "adapter_digest", "dictionary_digest", "registry_digest",
            "code_tree_oid", "code_closure_digest", "verifier_id", "signer_key_id",
            "protocol_version", "authority_session_id", "authority_request_id",
            "authority_nonce_digest", "caller_cdhash", "request_digest",
            "authority_cdhash", "verifier_cdhash",
            "source_payload_digest", "request_deadline_unix_ms", "authority_id",
            "signer_key_epoch", "signer_trust_digest",
            "verified_at_utc", "signature",
        }
        if (
            not isinstance(full_receipt, dict)
            or set(full_receipt) != required_receipt
            or full_receipt.get("schema_version")
            != "butler.box5.a4.verification_receipt.v5.3"
            or full_receipt.get("contract_id")
            != "BUTLER-BOX5-A4-V5.3-NATIVE-AUTHORITY"
            or full_receipt.get("run_id") != evidence_dir.name
            or full_receipt.get("decision") != "PASS"
            or full_receipt.get("reason_codes") != []
            or full_receipt.get("code_closure_digest")
            != expected_code_closure_digest
            or full_receipt.get("nonce") != run_document.get("nonce")
            or full_receipt.get("source_sha256")
            != input_document.get("source_file_sha256")
            or full_receipt.get("policy_digest") != run_document.get("policy_digest")
            or full_receipt.get("adapter_digest") != run_document.get("adapter_digest")
            or full_receipt.get("dictionary_digest")
            != run_document.get("dictionary_digest")
            or full_receipt.get("registry_digest") != run_document.get("registry_digest")
            or full_receipt.get("code_tree_oid") != run_document.get("code_tree_oid")
            or full_receipt.get("graph_digest") != digest_object(graph_document)
            or full_receipt.get("evidence_manifest_digest")
            != sha256_bytes((evidence_dir / "manifest.json").read_bytes())
            or full_receipt.get("verifier_id")
            != "BUTLER_A4_ISOLATED_RAW_COMPILER_V5.3"
        ):
            raise ValueError
    except (
        A4ContractError,
        KeyError,
        OSError,
        SchemaError,
        TypeError,
        ValidationError,
        ValueError,
    ) as exc:
        raise A4ContractError("BLOCK_SIGNATURE") from exc
    return full_receipt


def run_canonical_product_reconciliation(
    *,
    frame: Any | None,
    company_profile: Any,
    token_service: Any,
    store: ReconciliationProductStore,
    owner_request: Mapping[str, Any],
    policy_path: Path,
    trust_policy_path: Path,
    evidence_root: Path,
    observed_at: datetime,
    adapter: AdapterContract | None = None,
    verify_after_export: bool = True,
    source_snapshot: Any | None = None,
) -> dict[str, Any]:
    """Execute the only A4 product state machine; still shadow-only."""

    if getattr(company_profile, "status", None) != "ACTIVE":
        raise A4ContractError("BLOCK_ACCOUNT_IDENTITY")
    adapter = adapter or approved_split_adapter()
    required_owner = {
        "run_id",
        "nonce",
        "tenant_id",
        "code_tree_oid",
        "source_file_sha256",
        "source_file_size",
        "input_closure_digest",
    }
    if set(owner_request) != required_owner:
        raise A4ContractError("BLOCK_RUN_BINDING")
    queue_result = queue_canonical_product_reconciliation(
        store=store, owner_request=owner_request, observed_at=observed_at
    )
    if queue_result.get("state") == "PUBLISHED":
        export_from_outbox(
            store=store,
            tenant_id=str(owner_request["tenant_id"]),
            run_id=str(owner_request["run_id"]),
            evidence_root=evidence_root,
        )
        candidates = store.reconciliation_candidates(
            str(owner_request["tenant_id"]), str(owner_request["run_id"])
        )
        return {
            "run_id": str(owner_request["run_id"]),
            "state": "PUBLISHED",
            "forced_candidate_count": sum(item.get("kind") == "FORCED" for item in candidates),
            "ambiguous_component_count": sum(item.get("kind") == "AMBIGUOUS" for item in candidates),
            "affects_reporting": False,
            "journal_auto_post_allowed": False,
            "runtime_activation_allowed": False,
        }
    worker_stamp = observed_at.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    lease_until = (observed_at.astimezone(timezone.utc) + timedelta(minutes=5)).isoformat().replace(
        "+00:00", "Z"
    )
    store.claim_reconciliation_run(
        tenant_id=str(owner_request["tenant_id"]),
        run_id=str(owner_request["run_id"]),
        worker_owner_digest=digest_object(
            {"pid": os.getpid(), "run_id": owner_request["run_id"]}
        ),
        observed_at=worker_stamp,
        lease_expires_at=lease_until,
    )
    snapshot_receipt: Mapping[str, Any] | None = None
    if source_snapshot is not None:
        from butler_pc_core.accounting.classifier import read_source_frame_fd
        from .source_snapshot_v2_1 import physical_row_closure

        snapshot_receipt = source_snapshot.receipt
        if (
            snapshot_receipt.get("source_file_sha256")
            != owner_request["source_file_sha256"]
            or snapshot_receipt.get("source_file_size")
            != owner_request["source_file_size"]
        ):
            raise A4ContractError("BLOCK_INPUT_CLOSURE")
        frame = read_source_frame_fd(
            source_snapshot.producer_fd, source_snapshot.suffix
        )
        row_manifest = physical_row_closure(
            source_snapshot.producer_fd,
            source_snapshot.suffix,
            source_sha256=str(owner_request["source_file_sha256"]),
            adapter=adapter,
        )
    elif frame is None:
        raise A4ContractError("BLOCK_INPUT_CLOSURE")
    else:
        from .source_snapshot_v2_1 import row_closure

        row_manifest = row_closure(frame)
    registry = store.a4_own_account_registry(str(owner_request["tenant_id"]))
    compilation = compile_dataframe(
        frame=frame,
        tenant_id=str(owner_request["tenant_id"]),
        run_id=str(owner_request["run_id"]),
        source_file_sha256=str(owner_request["source_file_sha256"]),
        source_file_size=owner_request["source_file_size"],
        adapter=adapter,
        token_service=token_service,
        own_account_registry=registry,
    )
    if (
        source_snapshot is not None
        and row_manifest.get("transaction_row_count")
        != compilation.source_row_count
    ):
        raise A4ContractError("BLOCK_ROW_CLOSURE")
    try:
        if trust_policy_path.resolve(strict=True) != PINNED_TRUST_POLICY_PATH.resolve(
            strict=True
        ):
            raise A4ContractError("BLOCK_UNPINNED_KEY")
    except OSError as exc:
        raise A4ContractError("BLOCK_UNPINNED_KEY") from exc
    trust = load_trust_policy(trust_policy_path)
    policy_raw = policy_path.read_bytes()
    policy_document = strict_json_loads(policy_raw)
    if not isinstance(policy_document, dict) or not isinstance(
        policy_document.get("receipt"), dict
    ):
        raise A4ContractError("BLOCK_POLICY")
    receipt = policy_document["receipt"]
    expected = {
        "tenant_id": str(owner_request["tenant_id"]),
        "schema_digest": SCHEMA_DIGEST,
        "adapter_digest": compilation.adapter_digest,
        "account_snapshot_digest": compilation.account_snapshot_digest,
        "dictionary_digest": compilation.dictionary_digest,
        "registry_digest": compilation.registry_digest,
        "code_tree_oid": str(owner_request["code_tree_oid"]),
        "run_nonce_digest": sha256_bytes(bytes.fromhex(str(owner_request["nonce"]))),
    }
    policy = verify_signed_policy(
        policy_raw,
        trust=trust,
        expected=expected,
        now=observed_at.astimezone(timezone.utc),
    )
    binding = RunBinding(
        str(owner_request["run_id"]),
        str(owner_request["nonce"]),
        str(owner_request["tenant_id"]),
        str(owner_request["code_tree_oid"]),
        str(owner_request["input_closure_digest"]),
        compilation.adapter_digest,
        str(receipt["policy_digest"]),
        compilation.account_snapshot_digest,
        compilation.dictionary_digest,
        compilation.registry_digest,
    )
    result = reconcile(compilation.transactions, policy)
    evidence = _build_evidence(
        binding=binding,
        compilation=compilation,
        adapter=adapter,
        policy_document=policy_document,
        result=result,
        row_manifest=row_manifest,
        snapshot_receipt=snapshot_receipt,
    )
    run_record = {
        "tenant_id": binding.tenant_id,
        "run_id": binding.run_id,
        "nonce_digest": binding.nonce_digest,
        "code_tree_oid": binding.code_tree_oid,
        "input_closure_digest": binding.input_closure_digest,
        "dictionary_digest": binding.dictionary_digest,
        "created_at": observed_at.astimezone(timezone.utc)
        .isoformat()
        .replace("+00:00", "Z"),
    }
    store.commit_reconciliation_run(
        run=run_record,
        transactions=[item.safe_dict() for item in compilation.transactions],
        edges=[item.safe_dict() for item in result.edges],
        classifications=_classifications(result),
        policy_receipt=dict(receipt),
        evidence_payloads=evidence,
    )
    final = export_from_outbox(
        store=store,
        tenant_id=binding.tenant_id,
        run_id=binding.run_id,
        evidence_root=evidence_root,
    )
    if verify_after_export:
        if source_snapshot is None:
            raise A4ContractError("BLOCK_INPUT_CLOSURE")
        verification_receipt = verify_in_separate_process(
            evidence_dir=final,
            trust_policy_path=trust_policy_path,
            token_service=token_service,
            tenant_id=binding.tenant_id,
            source_fd=source_snapshot.verifier_fd,
            source_suffix=source_snapshot.suffix,
        )
        store.mark_reconciliation_verified(
            binding.tenant_id, binding.run_id, verification_receipt
        )
    return {
        "run_id": binding.run_id,
        "state": "PUBLISHED" if verify_after_export else "EVIDENCE_STAGED",
        "forced_candidate_count": len(result.forced_edges),
        "ambiguous_component_count": sum(
            component.has_alternative_optimum for component in result.components
        ),
        "affects_reporting": False,
        "journal_auto_post_allowed": False,
        "runtime_activation_allowed": False,
    }
