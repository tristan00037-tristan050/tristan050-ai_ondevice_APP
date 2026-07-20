"""Product orchestration and transactional evidence export for Box5 A4 v3.1."""

from __future__ import annotations

import hashlib
import os
import secrets
import shutil
import base64
import binascii
import tempfile

# Fixed argv launches only the repository-owned independent verifier.
import subprocess  # nosec B404
import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Mapping, Protocol

from jsonschema import Draft202012Validator, FormatChecker
from jsonschema.exceptions import SchemaError, ValidationError
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

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
CODE_CLOSURE_FILES = (
    "butler_pc_core/a4_verifier/cli.py",
    "butler_pc_core/accounting/assignment/a4_store_schema_v31.py",
    "butler_pc_core/accounting/classify/reconciliation_v2.py",
    "butler_pc_core/accounting/classify/reconciliation_service_v2.py",
    "butler_pc_core/accounting/classify/contracts/a4_v2/evidence_bundle.schema.json",
    "butler_pc_core/accounting/classify/contracts/a4_v31/code_dictionary.production.json",
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
    return {
        "schema_version": "2.0.0",
        "run_id": run_id,
        "forced_edges": forced,
        "components": [component.safe_dict(run_id) for component in result.components],
        "globally_unmatched_txn_uids": list(result.globally_unmatched_txn_uids),
        "shadow_only": True,
        "affects_reporting": False,
    }


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
    verifier = Path(__file__).resolve().parents[2] / "a4_verifier" / "cli.py"
    command = [
        sys.executable,
        "-I",
        str(verifier),
        "--evidence",
        str(evidence_dir),
        "--trust-policy",
        str(trust_policy_path),
        "--source-fd",
        str(source_fd),
        "--source-suffix",
        source_suffix,
        "--dictionary",
        str(CODE_DICTIONARY_PATH),
    ]
    if source_suffix != ".csv":
        raise A4ContractError("BLOCK_UNSUPPORTED_SOURCE_FORMAT")
    material = token_service.a4_verifier_material(tenant_id)
    with tempfile.TemporaryFile(mode="w+b") as key_file:
        key_file.write(jcs_bytes(material))
        key_file.flush()
        os.lseek(key_file.fileno(), 0, os.SEEK_SET)
        command.extend(["--key-material-fd", str(key_file.fileno())])
        # No shell; executable and script are repository/runtime-owned absolute paths.
        completed = subprocess.run(  # nosec B603
            command,
            cwd=str(Path(__file__).resolve().parents[3]),
            env={"PATH": os.environ.get("PATH", "")},
            capture_output=True,
            text=False,
            timeout=timeout_seconds,
            check=False,
            pass_fds=(source_fd, key_file.fileno()),
        )
    lines = completed.stdout.splitlines()
    if (
        completed.returncode != 0
        or len(lines) != 3
        or lines[0] != b"A4_VERIFY_PASS=1"
        or lines[1] != b"ERROR_CODE=NONE"
        or not lines[2].startswith(b"A4_VERIFICATION_RECEIPT_B64=")
    ):
        raise A4ContractError("BLOCK_OFFLINE_VERIFIER")
    try:
        encoded = lines[2].split(b"=", 1)[1]
        encoded += b"=" * (-len(encoded) % 4)
        full_receipt = strict_json_loads(base64.urlsafe_b64decode(encoded))
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
            "verified_at_utc", "signature",
        }
        if (
            not isinstance(full_receipt, dict)
            or set(full_receipt) != required_receipt
            or full_receipt.get("schema_version")
            != "butler.box5.a4.verification_receipt.v3.1"
            or full_receipt.get("contract_id")
            != "BUTLER-BOX5-A4-V3.1-CANONICAL-DIRECTIVE"
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
        ):
            raise ValueError
        signature_text = full_receipt.pop("signature")
        signature_raw = base64.urlsafe_b64decode(signature_text + "=" * (-len(signature_text) % 4))
        signer_key_id, public_raw = token_service.a4_verifier_public_key(tenant_id)
        if full_receipt.get("signer_key_id") != signer_key_id:
            raise ValueError
        Ed25519PublicKey.from_public_bytes(public_raw).verify(
            signature_raw, jcs_bytes(full_receipt)
        )
    except (
        A4ContractError,
        binascii.Error,
        InvalidSignature,
        KeyError,
        OSError,
        SchemaError,
        TypeError,
        ValidationError,
        ValueError,
    ) as exc:
        raise A4ContractError("BLOCK_SIGNATURE") from exc
    body = {
        "nonce": str(full_receipt["nonce"]),
        "evidence_manifest_digest": str(full_receipt["evidence_manifest_digest"]),
        "verifier_id": str(full_receipt["verifier_id"]),
        "signer_key_id": str(full_receipt["signer_key_id"]),
        "code_closure_digest": str(full_receipt["code_closure_digest"]),
        "decision": str(full_receipt["decision"]),
        "verified_at": str(full_receipt["verified_at_utc"]),
    }
    return {"receipt_digest": digest_object(body), **body}


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
        from .source_snapshot_v2_1 import row_closure

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
    elif frame is None:
        raise A4ContractError("BLOCK_INPUT_CLOSURE")
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
