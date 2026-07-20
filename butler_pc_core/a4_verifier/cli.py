#!/usr/bin/env python3
"""Independent, public-key-only verifier for Box5 A4 evidence.

The file is executable under ``python -I`` and contains its own parser,
canonicalizer, graph oracle, fee checks, and DLP rules.  Importing the producer
package is prohibited by construction and checked again in release tests.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import hmac
import json
import os
import re
import unicodedata
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any, Mapping, NoReturn, Sequence
from zoneinfo import ZoneInfo

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)


FILES = frozenset(
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
JSON_FILES = FILES - {"SHA256SUMS"}
SCHEMA_DIGEST = hashlib.sha256(b"butler.box5.a4.contracts.v3.1").hexdigest()
CODE_FILES = (
    "butler_pc_core/a4_verifier/cli.py",
    "butler_pc_core/accounting/assignment/a4_store_schema_v31.py",
    "butler_pc_core/accounting/classify/reconciliation_v2.py",
    "butler_pc_core/accounting/classify/reconciliation_service_v2.py",
    "butler_pc_core/accounting/classify/contracts/a4_v2/evidence_bundle.schema.json",
    "butler_pc_core/accounting/classify/contracts/a4_v31/code_dictionary.production.json",
    "butler_pc_core/accounting/classify/contracts/a4_v31/verification_receipt.schema.json",
)
MAX_MONEY = 9_000_000_000_000_000
NAMESPACE = uuid.UUID("b8f2ceca-9183-5c4a-9750-3e0ed0f87066")
HEADER_KEYWORDS = frozenset(
    {
        "거래일",
        "거래일시",
        "거래일자",
        "일자",
        "일시",
        "거래내용",
        "적요",
        "내역",
        "비고",
        "메모",
        "출금",
        "출금액",
        "출금금액",
        "지급",
        "입금",
        "입금액",
        "입금금액",
        "금액",
        "거래금액",
        "잔액",
        "거래후잔액",
        "거래후 잔액",
        "거래처",
        "상대처",
        "받는분",
        "보내는분",
        "상대계좌예금주명",
    }
)


class Block(Exception):
    pass


def block(code: str) -> NoReturn:
    raise Block(code if re.fullmatch(r"BLOCK_[A-Z0-9_]+", code) else "BLOCK_VERIFY")


def pairs_hook(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            block("BLOCK_DUPLICATE_KEY")
        result[key] = value
    return result


def strict_load(raw: bytes) -> Any:
    try:
        return json.loads(
            raw.decode("utf-8"),
            object_pairs_hook=pairs_hook,
            parse_constant=lambda _value: block("BLOCK_NUMBER"),
            parse_float=lambda _value: block("BLOCK_NUMBER"),
        )
    except Block:
        raise
    except Exception:
        block("BLOCK_SCHEMA")


def string_bytes(value: str) -> bytes:
    if any(0xD800 <= ord(char) <= 0xDFFF for char in value):
        block("BLOCK_SCHEMA")
    return json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


def jcs(value: Any) -> bytes:
    if value is None:
        return b"null"
    if value is True:
        return b"true"
    if value is False:
        return b"false"
    if type(value) is int:
        return str(value).encode("ascii")
    if isinstance(value, float):
        block("BLOCK_NUMBER")
    if isinstance(value, str):
        return string_bytes(value)
    if isinstance(value, list):
        return b"[" + b",".join(jcs(item) for item in value) + b"]"
    if isinstance(value, dict):
        if any(not isinstance(key, str) for key in value):
            block("BLOCK_SCHEMA")
        keys = sorted(value, key=lambda key: key.encode("utf-16-be", "surrogatepass"))
        return (
            b"{"
            + b",".join(string_bytes(key) + b":" + jcs(value[key]) for key in keys)
            + b"}"
        )
    block("BLOCK_SCHEMA")


def digest(value: Any) -> str:
    return hashlib.sha256(jcs(value)).hexdigest()


def read_files(root: Path) -> dict[str, bytes]:
    if root.is_symlink() or not root.is_dir():
        block("BLOCK_FILE_TYPE")
    observed: dict[str, bytes] = {}
    for item in root.iterdir():
        if item.name not in FILES:
            block("BLOCK_FILE_SET")
        mode = item.lstat().st_mode
        if (
            item.is_symlink()
            or not os.path.isfile(item)
            or not (mode & 0o170000) == 0o100000
        ):
            block("BLOCK_FILE_TYPE")
        observed[item.name] = item.read_bytes()
    if set(observed) != FILES:
        block("BLOCK_FILE_SET")
    return observed


def normalize_column(value: object) -> str:
    return re.sub(r"[\s　 ]+", "", re.sub(r"\(원\)", "", str(value)))


def normalized_cell(value: object) -> str:
    if value is None:
        return ""
    text = unicodedata.normalize("NFC", str(value)).strip()
    if len(text.encode("utf-8")) > 1_024:
        block("BLOCK_RESOURCE_LIMIT")
    return text


def read_source_frame(fd: int, suffix: str) -> Any:
    try:
        import pandas as pd
    except ImportError:
        block("BLOCK_VERIFIER_DEPENDENCY")

    def handle():
        duplicate = os.dup(fd)
        os.lseek(duplicate, 0, os.SEEK_SET)
        return os.fdopen(duplicate, "rb", closefd=True)

    if suffix == ".xlsx":
        try:
            import openpyxl
        except ImportError:
            block("BLOCK_VERIFIER_DEPENDENCY")
        with handle() as source:
            workbook = openpyxl.load_workbook(source, read_only=True, data_only=True)
            worksheet = workbook.active
            normalized_keywords = {normalize_column(item) for item in HEADER_KEYWORDS}
            best_row = 0
            best_score = 0.0
            for index, row in enumerate(
                worksheet.iter_rows(min_row=1, max_row=12, values_only=True)
            ):
                score = 0.0
                for cell in row:
                    if cell is None:
                        continue
                    text = normalize_column(str(cell).strip())
                    if text in normalized_keywords:
                        score += 1.0
                    elif any(keyword in text for keyword in normalized_keywords):
                        score += 0.5
                if score > best_score:
                    best_row, best_score = index, score
            workbook.close()
        with handle() as source:
            return pd.read_excel(source, header=best_row, dtype=str).fillna("")
    if suffix == ".xls":
        with handle() as source:
            return pd.read_excel(source, header=0, dtype=str).fillna("")
    if suffix != ".csv":
        block("BLOCK_FILE_TYPE")
    with handle() as source:
        raw = source.read()
    from io import BytesIO

    for encoding in ("utf-8-sig", "utf-8", "cp949", "euc-kr"):
        try:
            return pd.read_csv(BytesIO(raw), dtype=str, encoding=encoding).fillna("")
        except UnicodeDecodeError:
            continue
    block("BLOCK_INPUT_PARSE")


def rebuild_row_closure(frame: Any) -> dict[str, Any]:
    columns = tuple(str(column) for column in frame.columns)
    rows: list[dict[str, Any]] = []
    ordered = hashlib.sha256()
    for ordinal, (_, row) in enumerate(frame.iterrows()):
        cells = [[column, normalized_cell(row.get(column))] for column in columns]
        row_digest = digest(
            {"domain": "BUTLER_A4_PARSED_ROW_V2_1", "ordinal": ordinal, "cells": cells}
        )
        disposition = (
            "FEE"
            if normalized_cell(row.get("거래유형")).upper() in {"FEE", "수수료"}
            else "PRINCIPAL"
        )
        ordered.update(bytes.fromhex(row_digest))
        rows.append(
            {
                "ordinal": ordinal,
                "row_digest": row_digest,
                "disposition": disposition,
            }
        )
    return {
        "schema_version": "2.1.0",
        "ordered_row_root": ordered.hexdigest(),
        "row_count": len(rows),
        "disposition_counts": {
            name: sum(item["disposition"] == name for item in rows)
            for name in ("PRINCIPAL", "FEE", "HEADER", "QUARANTINED", "REJECTED")
        },
        "rows": rows,
    }


def verify_source_snapshot(fd: int, suffix: str, receipt: Mapping[str, Any]) -> None:
    os.lseek(fd, 0, os.SEEK_SET)
    source_digest = hashlib.sha256()
    size = 0
    while True:
        chunk = os.read(fd, 1024 * 1024)
        if not chunk:
            break
        source_digest.update(chunk)
        size += len(chunk)
    os.lseek(fd, 0, os.SEEK_SET)
    snapshot = receipt.get("source_snapshot_receipt")
    required = {
        "schema_version",
        "source_file_sha256",
        "source_file_size",
        "pre_fstat_digest",
        "post_fstat_digest",
        "snapshot_sha256",
        "producer_verifier_fd_separated",
        "snapshot_path_unlinked",
    }
    if (
        not isinstance(snapshot, dict)
        or set(snapshot) != required
        or snapshot.get("schema_version") != "2.1.0"
        or snapshot.get("producer_verifier_fd_separated") is not True
        or snapshot.get("snapshot_path_unlinked") is not True
        or source_digest.hexdigest() != receipt.get("source_file_sha256")
        or source_digest.hexdigest() != snapshot.get("snapshot_sha256")
        or size != receipt.get("source_file_size")
        or size != snapshot.get("source_file_size")
    ):
        block("BLOCK_INPUT_CLOSURE")
    frame = read_source_frame(fd, suffix)
    if rebuild_row_closure(frame) != receipt.get("row_closure"):
        block("BLOCK_ROW_CLOSURE")


def _field(value: str) -> bytes:
    raw = value.encode("utf-8")
    return len(raw).to_bytes(4, "big") + raw


def _key_material(fd: int, tenant_id: str) -> dict[str, Any]:
    os.lseek(fd, 0, os.SEEK_SET)
    raw = bytearray()
    while chunk := os.read(fd, 4096):
        raw.extend(chunk)
        if len(raw) > 16_384:
            block("BLOCK_RESOURCE_LIMIT")
    material = strict_load(bytes(raw))
    required = {
        "schema_version",
        "tenant_id",
        "key_id",
        "own_account_key_b64",
        "bank_reference_key_b64",
        "counterparty_account_key_b64",
        "run_transaction_key_b64",
        "verification_signing_seed_b64",
    }
    if (
        not isinstance(material, dict)
        or set(material) != required
        or material.get("schema_version") != "butler.box5.a4.verifier_keys.v3.1"
        or material.get("tenant_id") != tenant_id
    ):
        block("BLOCK_TRUST_UNAVAILABLE")
    for name in required - {"schema_version", "tenant_id", "key_id"}:
        try:
            decoded = base64.urlsafe_b64decode(str(material[name]))
        except Exception:
            block("BLOCK_TRUST_UNAVAILABLE")
        if len(decoded) != 32:
            block("BLOCK_TRUST_UNAVAILABLE")
        material[name] = decoded
    return material


def _dictionary(path: Path, expected_digest: str) -> dict[str, Any]:
    if path.is_symlink() or not path.is_file():
        block("BLOCK_DICTIONARY_VALUE")
    raw = path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != expected_digest:
        block("BLOCK_DICTIONARY_VALUE")
    document = strict_load(raw)
    if (
        not isinstance(document, dict)
        or set(document)
        != {
            "schema_version", "dictionary_id", "version", "unknown_policy",
            "product_codes", "channels",
        }
        or document.get("schema_version") != "butler.box5.a4.code_dictionary.v3.1"
        or document.get("unknown_policy") != "QUARANTINE"
    ):
        block("BLOCK_DICTIONARY_VALUE")

    def aliases(items: Any) -> dict[str, str]:
        result: dict[str, str] = {}
        if not isinstance(items, list) or not items:
            block("BLOCK_DICTIONARY_VALUE")
        for item in items:
            if not isinstance(item, dict) or set(item) != {"id", "aliases"}:
                block("BLOCK_DICTIONARY_VALUE")
            stable_id = str(item["id"])
            if not re.fullmatch(r"[A-Za-z0-9._:-]{1,96}", stable_id):
                block("BLOCK_DICTIONARY_VALUE")
            for alias in item["aliases"]:
                key = unicodedata.normalize("NFC", str(alias)).strip().upper()
                if not key or key in result:
                    block("BLOCK_DICTIONARY_VALUE")
                result[key] = stable_id
        if "DEFAULT" not in result.values():
            block("BLOCK_DICTIONARY_VALUE")
        return result

    return {
        "product": aliases(document["product_codes"]),
        "channel": aliases(document["channels"]),
    }


def _account_number(value: Any) -> str:
    return re.sub(r"[^0-9A-Za-z]", "", normalized_cell(value).upper())


def _token(key: bytes, *values: str) -> str:
    return hmac.new(key, b"".join(_field(value) for value in values), hashlib.sha256).hexdigest()


def _source_amount(value: Any) -> int:
    text = normalized_cell(value)
    if not re.fullmatch(r"(?:0|[1-9][0-9]{0,18}|[1-9][0-9]{0,2}(?:,[0-9]{3})+)", text):
        block("BLOCK_SOURCE_SEMANTIC_MISMATCH")
    amount = int(text.replace(",", ""))
    if not 1 <= amount <= MAX_MONEY:
        block("BLOCK_RANGE")
    return amount


def independently_compile_source(
    frame: Any,
    input_receipt: Mapping[str, Any],
    run: Mapping[str, Any],
    accounts: Sequence[Mapping[str, Any]],
    material: Mapping[str, Any],
    dictionary: Mapping[str, Mapping[str, str]],
) -> list[dict[str, Any]]:
    """Compile raw rows without importing or calling producer code."""

    adapter = input_receipt.get("adapter_contract")
    if not isinstance(adapter, dict):
        block("BLOCK_SOURCE_SEMANTIC_MISMATCH")
    columns = {unicodedata.normalize("NFC", str(value)).strip(): value for value in frame.columns}
    names = {
        key: adapter.get(key)
        for key in (
            "source_account", "bank_code", "booking_date", "withdrawal", "deposit",
            "reference", "counter_account", "fee_type", "product_code", "channel",
        )
    }
    for key in ("source_account", "bank_code", "booking_date", "withdrawal", "deposit"):
        if names[key] not in columns:
            block("BLOCK_SOURCE_SEMANTIC_MISMATCH")
    registry: dict[tuple[str, str, str], str] = {}
    for account in accounts:
        try:
            key = (
                str(account["bank_code"]),
                str(account["lookup_key_id"]),
                str(account["lookup_token"]),
            )
            registry[key] = uuid_string(account["account_id"])
        except Exception:
            block("BLOCK_REGISTRY_IDENTITY")
    rows = tuple(frame.iterrows())
    identities: dict[tuple[str, str], tuple[str, str]] = {}
    number_ids: dict[str, set[str]] = {}
    tenant = str(run["tenant_id"])
    for _, row in rows:
        bank = normalized_cell(row.get(columns[names["bank_code"]])).upper()
        number = _account_number(row.get(columns[names["source_account"]]))
        account_token = _token(material["own_account_key_b64"], tenant, bank, number)
        account_id = registry.get((bank, str(material["key_id"]), account_token))
        if not bank or not number or account_id is None:
            block("BLOCK_REGISTRY_IDENTITY")
        identities[(bank, number)] = (account_id, account_token)
        number_ids.setdefault(number, set()).add(account_id)
    namespace = uuid.uuid5(uuid.UUID(tenant), str(input_receipt["source_file_sha256"]))
    rebuilt: list[dict[str, Any]] = []
    artifacts: set[str] = set()
    formats = adapter.get("allowed_date_formats")
    if not isinstance(formats, list):
        block("BLOCK_SOURCE_SEMANTIC_MISMATCH")
    for ordinal, (_, row) in enumerate(rows):
        withdrawal = normalized_cell(row.get(columns[names["withdrawal"]]))
        deposit = normalized_cell(row.get(columns[names["deposit"]]))
        if bool(withdrawal) == bool(deposit):
            block("BLOCK_SOURCE_SEMANTIC_MISMATCH")
        direction = "OUTFLOW" if withdrawal else "INFLOW"
        amount = _source_amount(withdrawal or deposit)
        bank = normalized_cell(row.get(columns[names["bank_code"]])).upper()
        number = _account_number(row.get(columns[names["source_account"]]))
        identity = identities.get((bank, number))
        if identity is None:
            block("BLOCK_REGISTRY_IDENTITY")
        account_id = identity[0]
        parsed = None
        raw_date = normalized_cell(row.get(columns[names["booking_date"]]))
        for date_format in formats:
            try:
                parsed = datetime.strptime(raw_date, str(date_format))
                break
            except ValueError:
                continue
        if parsed is None:
            block("BLOCK_SOURCE_SEMANTIC_MISMATCH")
        local_date = parsed.date().isoformat()
        booked_at = parsed.replace(tzinfo=ZoneInfo(str(adapter["zone_name"]))).astimezone(timezone.utc)
        booked_at_text = booked_at.isoformat().replace("+00:00", "Z")
        reference_token = None
        if names["reference"] in columns:
            reference = normalized_cell(row.get(columns[names["reference"]]))
            if reference:
                reference_token = _token(
                    material["bank_reference_key_b64"], tenant, "BANK_REFERENCE", reference
                )
        counter_token = None
        resolved = None
        resolution = "MISSING"
        if names["counter_account"] in columns:
            raw_counter = normalized_cell(row.get(columns[names["counter_account"]]))
            counter = _account_number(raw_counter)
            if any(marker in raw_counter for marker in ("*", "•", "●")):
                resolution = "MASKED"
            elif counter:
                counter_token = _token(
                    material["counterparty_account_key_b64"],
                    tenant,
                    "COUNTERPARTY_ACCOUNT",
                    counter,
                )
                candidates = number_ids.get(counter, set())
                if len(candidates) == 1:
                    resolved, resolution = next(iter(candidates)), "EXACT_VERIFIED"
                elif len(candidates) > 1:
                    block("BLOCK_COUNTERPARTY_CONFLICT")
                else:
                    resolution = "UNRESOLVED"
        row_kind = "PRINCIPAL"
        if names["fee_type"] in columns:
            fee = normalized_cell(row.get(columns[names["fee_type"]])).upper()
            if fee:
                if fee not in {"FEE", "수수료"}:
                    block("BLOCK_SOURCE_SEMANTIC_MISMATCH")
                row_kind = "FEE"
        product_value = "DEFAULT"
        if names["product_code"] in columns:
            product_value = normalized_cell(row.get(columns[names["product_code"]])) or "DEFAULT"
        channel_value = "DEFAULT"
        if names["channel"] in columns:
            channel_value = normalized_cell(row.get(columns[names["channel"]])) or "DEFAULT"
        product_id = dictionary["product"].get(product_value.upper())
        channel_id = dictionary["channel"].get(channel_value.upper())
        if product_id is None or channel_id is None:
            block("BLOCK_DICTIONARY_VALUE")
        canonical = {
            "account_id": account_id,
            "direction": direction,
            "amount_minor": amount,
            "currency": "KRW",
            "booked_at_utc": booked_at_text,
            "local_date": local_date,
            "bank_code": bank,
            "bank_reference_token": reference_token,
            "counterparty_account_token": counter_token,
            "resolved_counterparty_account_id": resolved,
            "counterparty_resolution": resolution,
            "row_kind": row_kind,
            "product_code_id": product_id,
            "channel_id": channel_id,
            "adapter_id": adapter["adapter_id"],
            "adapter_digest": run["adapter_digest"],
            "registry_digest": run["registry_digest"],
        }
        canonical_digest = digest(canonical)
        source_row_digest = digest(
            {
                "source_file_sha256": input_receipt["source_file_sha256"],
                "row_ordinal": ordinal,
                "canonical_row_sha256": canonical_digest,
            }
        )
        txn_uid = str(uuid.uuid5(
            namespace,
            f"{input_receipt['source_file_sha256']}:{ordinal}:{canonical_digest}",
        ))
        artifact = _token(
            material["run_transaction_key_b64"],
            tenant,
            "RUN_TRANSACTION",
            str(run["run_id"]) + tenant + txn_uid,
        )[:32]
        if artifact in artifacts:
            block("BLOCK_ARTIFACT_TOKEN_COLLISION")
        artifacts.add(artifact)
        rebuilt.append(
            {
                "tenant_id": tenant,
                "txn_uid": txn_uid,
                "source_row_digest": source_row_digest,
                "row_ordinal": ordinal,
                "canonical_row_digest": canonical_digest,
                "account_id": account_id,
                "direction": direction,
                "amount_minor": amount,
                "currency": "KRW",
                "booked_at_utc": booked_at_text,
                "local_date": local_date,
                "artifact_token": artifact,
                "bank_code": bank,
                "bank_reference_token": reference_token,
                "counterparty_account_token": counter_token,
                "resolved_counterparty_account_id": resolved,
                "counterparty_resolution": resolution,
                "row_kind": row_kind,
                "product_code_id": product_id,
                "channel_id": channel_id,
                "adapter_id": adapter["adapter_id"],
                "adapter_digest": run["adapter_digest"],
                "registry_digest": run["registry_digest"],
            }
        )
    return sorted(rebuilt, key=lambda item: (item["tenant_id"], item["txn_uid"]))


def verify_hashes(raw: Mapping[str, bytes], docs: Mapping[str, Any]) -> None:
    expected_lines = b"".join(
        f"{hashlib.sha256(raw[name]).hexdigest()}  {name}\n".encode("ascii")
        for name in sorted(JSON_FILES)
    )
    if raw["SHA256SUMS"] != expected_lines:
        block("BLOCK_DIGEST")
    manifest = docs["manifest.json"]
    if not isinstance(manifest, dict) or set(manifest) != {
        "schema_version",
        "run_id",
        "nonce_digest",
        "code_tree_oid",
        "files",
    }:
        block("BLOCK_SCHEMA")
    files = manifest["files"]
    if not isinstance(files, list) or len(files) != 8:
        block("BLOCK_FILE_SET")
    observed: dict[str, tuple[str, int]] = {}
    for item in files:
        if not isinstance(item, dict) or set(item) != {"path", "sha256", "size"}:
            block("BLOCK_SCHEMA")
        path = item["path"]
        if path in observed or path not in JSON_FILES - {"manifest.json"}:
            block("BLOCK_FILE_SET")
        observed[path] = (item["sha256"], item["size"])
    if set(observed) != JSON_FILES - {"manifest.json"}:
        block("BLOCK_FILE_SET")
    for name, (sha, size) in observed.items():
        if (
            type(size) is not int
            or size != len(raw[name])
            or sha != hashlib.sha256(raw[name]).hexdigest()
        ):
            block("BLOCK_DIGEST")


def parse_time(value: Any) -> datetime:
    if not isinstance(value, str) or not value.endswith("Z"):
        block("BLOCK_TIMEZONE")
    try:
        result = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError:
        block("BLOCK_TIMEZONE")
    if result.tzinfo is None or result.utcoffset() != timezone.utc.utcoffset(result):
        block("BLOCK_TIMEZONE")
    return result


def load_trust(path: Path) -> dict[str, Any]:
    if path.is_symlink() or not path.is_file():
        block("BLOCK_UNPINNED_KEY")
    trust = strict_load(path.read_bytes())
    required = {
        "schema_version",
        "policy_type",
        "algorithm",
        "expected_signer_key_id",
        "public_key_b64",
        "revocation_epoch",
        "enabled",
    }
    if not isinstance(trust, dict) or set(trust) != required:
        block("BLOCK_UNPINNED_KEY")
    if (
        trust["schema_version"] != "1.0.0"
        or trust["enabled"] is not True
        or trust["policy_type"] != "A4_RECON_POLICY"
        or trust["algorithm"] != "Ed25519"
    ):
        block("BLOCK_UNPINNED_KEY")
    if type(trust["revocation_epoch"]) is not int or trust["revocation_epoch"] < 0:
        block("BLOCK_UNPINNED_KEY")
    return trust


def verify_policy(
    receipt: Any, payload: Any, trust: Mapping[str, Any], expected: Mapping[str, str]
) -> dict[str, Any]:
    required = {
        "policy_type",
        "policy_id",
        "policy_version",
        "policy_digest",
        "finance_approval_id",
        "finance_approver_role",
        "signer_key_id",
        "issued_at",
        "effective_from",
        "expires_at",
        "revocation_epoch",
        "tenant_id",
        "schema_digest",
        "adapter_digest",
        "account_snapshot_digest",
        "dictionary_digest",
        "registry_digest",
        "code_tree_oid",
        "run_nonce_digest",
        "signature_b64",
    }
    if (
        not isinstance(receipt, dict)
        or set(receipt) != required
        or not isinstance(payload, dict)
    ):
        block("BLOCK_POLICY")
    if (
        receipt["policy_type"] != trust["policy_type"]
        or receipt["signer_key_id"] != trust["expected_signer_key_id"]
    ):
        block("BLOCK_SIGNER")
    if receipt["finance_approver_role"] != "FINANCE_APPROVER":
        block("BLOCK_SIGNER")
    if receipt["revocation_epoch"] != trust["revocation_epoch"]:
        block("BLOCK_REVOKED")
    for key in (
        "tenant_id",
        "schema_digest",
        "adapter_digest",
        "account_snapshot_digest",
        "dictionary_digest",
        "registry_digest",
        "code_tree_oid",
        "run_nonce_digest",
    ):
        if receipt[key] != expected[key]:
            block("BLOCK_BINDING")
    now = datetime.now(timezone.utc)
    issued, start, expires = (
        parse_time(receipt[key])
        for key in ("issued_at", "effective_from", "expires_at")
    )
    if not issued <= now <= expires or now < start or expires <= start:
        block("BLOCK_EXPIRED")
    if receipt["policy_digest"] != digest(payload):
        block("BLOCK_DIGEST")
    unsigned = {key: value for key, value in receipt.items() if key != "signature_b64"}
    try:
        public = base64.b64decode(trust["public_key_b64"], validate=True)
        signature = base64.b64decode(receipt["signature_b64"], validate=True)
        Ed25519PublicKey.from_public_bytes(public).verify(
            signature, jcs({"receipt": unsigned, "payload": payload})
        )
    except (ValueError, TypeError, InvalidSignature):
        block("BLOCK_SIGNATURE")
    return payload


def uuid_string(value: Any) -> str:
    if not isinstance(value, str):
        block("BLOCK_SCHEMA")
    try:
        parsed = str(uuid.UUID(value))
    except ValueError:
        block("BLOCK_SCHEMA")
    if parsed != value.lower():
        block("BLOCK_SCHEMA")
    return parsed


def verify_bindings(
    docs: Mapping[str, Any],
) -> tuple[dict[str, Any], list[dict[str, Any]], dict[str, Any]]:
    run = docs["run_request.json"]
    input_receipt = docs["input_receipt.json"]
    account = docs["account_snapshot_receipt.json"]
    if not all(isinstance(item, dict) for item in (run, input_receipt, account)):
        block("BLOCK_SCHEMA")
    required_run = {
        "schema_version",
        "run_id",
        "nonce",
        "tenant_id",
        "code_tree_oid",
        "input_closure_digest",
        "adapter_digest",
        "policy_digest",
        "account_snapshot_digest",
        "dictionary_digest",
        "registry_digest",
    }
    if set(run) != required_run or run["schema_version"] != "1.0.0":
        block("BLOCK_SCHEMA")
    run_id, tenant = uuid_string(run["run_id"]), uuid_string(run["tenant_id"])
    if not re.fullmatch(r"[0-9a-fA-F]{64}", run["nonce"]):
        block("BLOCK_RUN_BINDING")
    nonce_digest = hashlib.sha256(bytes.fromhex(run["nonce"])).hexdigest()
    for name in (
        "input_receipt.json",
        "account_snapshot_receipt.json",
        "graph_observation.json",
        "classification_receipt.json",
        "runtime_invariants.json",
        "dlp_receipt.json",
        "manifest.json",
    ):
        item = docs[name]
        if item.get("run_id") != run_id:
            block("BLOCK_RUN_BINDING")
        if "nonce_digest" in item and item["nonce_digest"] != nonce_digest:
            block("BLOCK_RUN_BINDING")
    if input_receipt.get("tenant_id") != tenant or account.get("tenant_id") != tenant:
        block("BLOCK_TENANT")
    source = {
        "source_file_sha256": input_receipt.get("source_file_sha256"),
        "source_file_size": input_receipt.get("source_file_size"),
    }
    if (
        digest(source) != run["input_closure_digest"]
        or input_receipt.get("input_closure_digest") != run["input_closure_digest"]
    ):
        block("BLOCK_INPUT_CLOSURE")
    adapter = input_receipt.get("adapter_contract")
    if (
        not isinstance(adapter, dict)
        or digest(adapter) != run["adapter_digest"]
        or input_receipt.get("adapter_digest") != run["adapter_digest"]
        or input_receipt.get("dictionary_digest") != run["dictionary_digest"]
        or input_receipt.get("registry_digest") != run["registry_digest"]
    ):
        block("BLOCK_BINDING")
    accounts = account.get("accounts")
    if (
        not isinstance(accounts, list)
        or digest(accounts) != run["account_snapshot_digest"]
        or account.get("account_snapshot_digest") != run["account_snapshot_digest"]
        or account.get("registry_digest") != run["registry_digest"]
    ):
        block("BLOCK_BINDING")
    txs = input_receipt.get("compiled_transactions")
    row_closure = input_receipt.get("row_closure")
    if (
        not isinstance(txs, list)
        or not isinstance(row_closure, dict)
        or input_receipt.get("source_row_count") != len(txs)
        or row_closure.get("row_count") != len(txs)
        or not isinstance(row_closure.get("rows"), list)
        or len(row_closure["rows"]) != len(txs)
    ):
        block("BLOCK_SCHEMA")
    namespace = uuid.uuid5(uuid.UUID(tenant), input_receipt["source_file_sha256"])
    uids: dict[str, str] = {}
    rows: dict[str, str] = {}
    artifacts: set[str] = set()
    account_ids = {
        item.get("account_id") for item in accounts if isinstance(item, dict)
    }
    for tx in txs:
        required_tx = {
            "tenant_id",
            "txn_uid",
            "source_row_digest",
            "row_ordinal",
            "canonical_row_digest",
            "account_id",
            "direction",
            "amount_minor",
            "currency",
            "booked_at_utc",
            "local_date",
            "artifact_token",
            "bank_code",
            "bank_reference_token",
            "counterparty_account_token",
            "resolved_counterparty_account_id",
            "counterparty_resolution",
            "row_kind",
            "product_code_id",
            "channel_id",
            "adapter_id",
            "adapter_digest",
            "registry_digest",
        }
        if not isinstance(tx, dict) or set(tx) != required_tx:
            block("BLOCK_SCHEMA")
        uid = uuid_string(tx.get("txn_uid"))
        if tx.get("tenant_id") != tenant or tx.get("account_id") not in account_ids:
            block("BLOCK_TENANT")
        ordinal, canonical = tx.get("row_ordinal"), tx.get("canonical_row_digest")
        if (
            type(ordinal) is not int
            or ordinal < 0
            or not re.fullmatch(r"[0-9a-f]{64}", str(canonical))
        ):
            block("BLOCK_SCHEMA")
        row_digest = digest(
            {
                "source_file_sha256": input_receipt["source_file_sha256"],
                "row_ordinal": ordinal,
                "canonical_row_sha256": canonical,
            }
        )
        if tx.get("source_row_digest") != row_digest:
            block("BLOCK_DIGEST")
        expected_uid = str(
            uuid.uuid5(
                namespace,
                f"{input_receipt['source_file_sha256']}:{ordinal}:{canonical}",
            )
        )
        if uid != expected_uid:
            block("BLOCK_TXN_UID_CONFLICT")
        if uid in uids and uids[uid] != row_digest:
            block("BLOCK_TXN_UID_CONFLICT")
        if row_digest in rows and rows[row_digest] != uid:
            block("BLOCK_DUPLICATE_SOURCE_ROW")
        token = tx.get("artifact_token")
        if (
            not isinstance(token, str)
            or not re.fullmatch(r"[0-9a-f]{32}", token)
            or token in artifacts
        ):
            block("BLOCK_ARTIFACT_TOKEN_COLLISION")
        amount = tx.get("amount_minor")
        if type(amount) is not int or not 1 <= amount <= MAX_MONEY:
            block("BLOCK_RANGE")
        if tx.get("currency") != "KRW" or tx.get("direction") not in {
            "INFLOW",
            "OUTFLOW",
        }:
            block("BLOCK_SCHEMA")
        if (
            tx.get("adapter_id") != adapter.get("adapter_id")
            or tx.get("adapter_digest") != run["adapter_digest"]
            or tx.get("registry_digest") != run["registry_digest"]
            or not re.fullmatch(r"[A-Za-z0-9._:-]{1,96}", str(tx.get("product_code_id")))
            or not re.fullmatch(r"[A-Za-z0-9._:-]{1,96}", str(tx.get("channel_id")))
        ):
            block("BLOCK_BINDING")
        resolution = tx.get("counterparty_resolution")
        resolved = tx.get("resolved_counterparty_account_id")
        if resolution not in {
            "EXACT_VERIFIED",
            "MASKED",
            "MISSING",
            "UNRESOLVED",
            "CONFLICT",
        }:
            block("BLOCK_SCHEMA")
        if resolution == "CONFLICT":
            block("BLOCK_COUNTERPARTY_CONFLICT")
        if resolution == "EXACT_VERIFIED":
            if uuid_string(resolved) not in account_ids:
                block("BLOCK_ACCOUNT_IDENTITY")
        elif resolved is not None:
            block("BLOCK_ACCOUNT_IDENTITY")
        parse_time(tx.get("booked_at_utc"))
        uids[uid], rows[row_digest] = row_digest, uid
        artifacts.add(token)
    expected = {
        "tenant_id": tenant,
        "schema_digest": SCHEMA_DIGEST,
        "adapter_digest": run["adapter_digest"],
        "account_snapshot_digest": run["account_snapshot_digest"],
        "dictionary_digest": run["dictionary_digest"],
        "registry_digest": run["registry_digest"],
        "code_tree_oid": run["code_tree_oid"],
        "run_nonce_digest": nonce_digest,
    }
    return run, txs, expected


def exact_ref(left: Mapping[str, Any], right: Mapping[str, Any]) -> bool:
    return bool(left.get("bank_reference_token")) and left.get(
        "bank_reference_token"
    ) == right.get("bank_reference_token")


def edge_digest(edge: Mapping[str, Any]) -> str:
    return digest(
        {
            "outflow": edge["outflow_txn_uid"],
            "inflow": edge["inflow_txn_uid"],
            "fee": edge["fee_txn_uid"],
            "mode": edge["fee_mode"],
            "fee_minor": edge["fee_minor"],
            "eligibility_basis": edge["eligibility_basis"],
            "binding_digest": edge["binding_digest"],
        }
    )


def rebuild_edges(
    txs: Sequence[dict[str, Any]], policy: Mapping[str, Any]
) -> tuple[list[dict[str, Any]], int, int]:
    required_policy = {
        "min_signed_gap_days",
        "max_signed_gap_days",
        "max_component_nodes",
        "max_candidate_edges",
        "max_transactions",
        "max_pair_checks",
        "max_trace_bucket",
        "max_memory_bytes",
        "fee_rules",
    }
    if set(policy) != required_policy or not isinstance(policy["fee_rules"], list):
        block("BLOCK_POLICY")
    caps = (
        policy["max_transactions"],
        policy["max_pair_checks"],
        policy["max_trace_bucket"],
        policy["max_memory_bytes"],
        policy["max_candidate_edges"],
    )
    if any(type(value) is not int or value <= 0 for value in caps):
        block("BLOCK_POLICY")
    if len(txs) > policy["max_transactions"]:
        block("BLOCK_RESOURCE_TRANSACTION_COUNT")
    if len(txs) * 2_048 > policy["max_memory_bytes"]:
        block("BLOCK_RESOURCE_MEMORY")
    principals = sorted(
        (tx for tx in txs if tx.get("row_kind") == "PRINCIPAL"),
        key=lambda tx: tx["txn_uid"],
    )
    fees = [tx for tx in txs if tx.get("row_kind") == "FEE"]
    inflow_index: dict[tuple[str, str, str, int], list[dict[str, Any]]] = {}
    for inflow in principals:
        if inflow["direction"] == "INFLOW":
            key = (
                inflow["tenant_id"],
                inflow["account_id"],
                inflow["currency"],
                inflow["amount_minor"],
            )
            inflow_index.setdefault(key, []).append(inflow)
    for bucket in inflow_index.values():
        bucket.sort(key=lambda tx: (tx["booked_at_utc"], tx["txn_uid"]))
    fee_index: dict[tuple[str, str, str, str], list[dict[str, Any]]] = {}
    for fee in fees:
        reference = fee.get("bank_reference_token")
        if reference:
            key = (
                fee["tenant_id"],
                fee["account_id"],
                fee["currency"],
                reference,
            )
            fee_index.setdefault(key, []).append(fee)
    for bucket in fee_index.values():
        bucket.sort(key=lambda tx: (tx["booked_at_utc"], tx["txn_uid"]))
    result: dict[str, dict[str, Any]] = {}
    pair_checks = 0
    max_bucket_size = 0
    for outflow in principals:
        if (
            outflow["direction"] != "OUTFLOW"
            or outflow["counterparty_resolution"] != "EXACT_VERIFIED"
            or outflow["resolved_counterparty_account_id"] is None
        ):
            continue
        amount_rules: dict[int, dict[str, Any] | None] = {outflow["amount_minor"]: None}
        at = parse_time(outflow["booked_at_utc"])
        for rule in policy["fee_rules"]:
            if not isinstance(rule, dict) or type(rule.get("fee_minor")) is not int:
                block("BLOCK_POLICY")
            principal_amount = outflow["amount_minor"] - rule["fee_minor"]
            if principal_amount <= 0:
                continue
            if (
                rule.get("bank_code") == outflow["bank_code"]
                and rule.get("product_code") == outflow["product_code_id"]
                and rule.get("channel") == outflow["channel_id"]
                and type(rule.get("min_amount_minor")) is int
                and rule["min_amount_minor"]
                <= principal_amount
                <= rule.get("max_amount_minor", -1)
                and parse_time(rule["effective_from"])
                <= at
                <= parse_time(rule["effective_to"])
            ):
                if (
                    principal_amount in amount_rules
                    and amount_rules[principal_amount] is not None
                ):
                    block("BLOCK_AMBIGUOUS_FEE_RULE")
                amount_rules[principal_amount] = rule
        for principal_amount in sorted(amount_rules):
            bucket = inflow_index.get(
                (
                    outflow["tenant_id"],
                    outflow["resolved_counterparty_account_id"],
                    outflow["currency"],
                    principal_amount,
                ),
                [],
            )
            max_bucket_size = max(max_bucket_size, len(bucket))
            if len(bucket) > policy["max_trace_bucket"]:
                block("BLOCK_RESOURCE_TRACE_BUCKET")
            for inflow in bucket:
                pair_checks += 1
                if pair_checks > policy["max_pair_checks"]:
                    block("BLOCK_RESOURCE_PAIR_CHECKS")
                if (
                    inflow["counterparty_resolution"] != "EXACT_VERIFIED"
                    or inflow["resolved_counterparty_account_id"]
                    != outflow["account_id"]
                    or outflow["account_id"] == inflow["account_id"]
                ):
                    continue
                left_day = datetime.fromisoformat(outflow["local_date"]).date()
                right_day = datetime.fromisoformat(inflow["local_date"]).date()
                gap = (right_day - left_day).days
                if (
                    not policy["min_signed_gap_days"]
                    <= gap
                    <= policy["max_signed_gap_days"]
                ):
                    continue
                time_delta = int(
                    abs(
                        (
                            parse_time(inflow["booked_at_utc"])
                            - parse_time(outflow["booked_at_utc"])
                        ).total_seconds()
                    )
                    * 1000
                )
                basis = "RECIPROCAL_ACCOUNT"
                binding = digest(
                    {
                        "domain": "BUTLER_A4_STRONG_BINDING_V2_1",
                        "tenant_id": outflow["tenant_id"],
                        "outflow_account_id": outflow["account_id"],
                        "inflow_account_id": inflow["account_id"],
                        "outflow_resolved_counterparty_account_id": outflow[
                            "resolved_counterparty_account_id"
                        ],
                        "inflow_resolved_counterparty_account_id": inflow[
                            "resolved_counterparty_account_id"
                        ],
                        "eligibility_basis": basis,
                    }
                )
                candidates: list[dict[str, Any]] = []
                common = {
                    "outflow_txn_uid": outflow["txn_uid"],
                    "inflow_txn_uid": inflow["txn_uid"],
                    "currency": outflow["currency"],
                    "time_delta_ms": time_delta,
                    "exact_reference": exact_ref(outflow, inflow),
                    "eligibility_basis": basis,
                    "binding_digest": binding,
                    "affects_reporting": False,
                }
                if outflow["amount_minor"] == inflow["amount_minor"]:
                    fee_bucket = (
                        fee_index.get(
                            (
                                outflow["tenant_id"],
                                outflow["account_id"],
                                outflow["currency"],
                                outflow["bank_reference_token"],
                            ),
                            [],
                        )
                        if outflow.get("bank_reference_token")
                        else []
                    )
                    matching_fees = [
                        fee
                        for fee in fee_bucket
                        if fee["direction"] == "OUTFLOW"
                        and abs(
                            (
                                parse_time(fee["booked_at_utc"])
                                - parse_time(outflow["booked_at_utc"])
                            ).total_seconds()
                        )
                        <= 86400
                    ]
                    if matching_fees:
                        for fee in matching_fees:
                            candidates.append(
                                {
                                    **common,
                                    "fee_txn_uid": fee["txn_uid"],
                                    "fee_mode": "SEPARATE_FEE_ROW",
                                    "fee_minor": fee["amount_minor"],
                                    "evidence_grade": "OBSERVED_FEE",
                                    "policy_rule_id": None,
                                }
                            )
                    else:
                        candidates.append(
                            {
                                **common,
                                "fee_txn_uid": None,
                                "fee_mode": "NO_FEE",
                                "fee_minor": 0,
                                "evidence_grade": "OBSERVED_PRINCIPAL",
                                "policy_rule_id": None,
                            }
                        )
                elif outflow["amount_minor"] > inflow["amount_minor"]:
                    delta = outflow["amount_minor"] - inflow["amount_minor"]
                    rule = amount_rules.get(inflow["amount_minor"])
                    if rule is not None and rule["fee_minor"] == delta:
                        candidates.append(
                            {
                                **common,
                                "fee_txn_uid": None,
                                "fee_mode": "EMBEDDED_DEBIT",
                                "fee_minor": delta,
                                "evidence_grade": "SCHEDULE_SUPPORTED_FEE_CANDIDATE",
                                "policy_rule_id": rule["rule_id"],
                            }
                        )
                for candidate in candidates:
                    candidate["edge_id"] = edge_digest(candidate)
                    result[candidate["edge_id"]] = candidate
                    if len(result) > policy["max_candidate_edges"]:
                        block("BLOCK_RESOURCE_LIMIT")
    return [result[key] for key in sorted(result)], pair_checks, max_bucket_size


def edge_nodes(edge: Mapping[str, Any]) -> frozenset[str]:
    return frozenset(
        value
        for value in (
            edge["outflow_txn_uid"],
            edge["inflow_txn_uid"],
            edge["fee_txn_uid"],
        )
        if value
    )


def components(edges: Sequence[dict[str, Any]]) -> list[list[dict[str, Any]]]:
    by_node: dict[str, list[dict[str, Any]]] = {}
    for edge in edges:
        for node in edge_nodes(edge):
            by_node.setdefault(node, []).append(edge)
    unseen = set(by_node)
    output = []
    while unseen:
        stack, found = [min(unseen)], {}
        unseen.remove(stack[0])
        while stack:
            node = stack.pop()
            for edge in by_node[node]:
                found[edge["edge_id"]] = edge
                for other in edge_nodes(edge):
                    if other in unseen:
                        unseen.remove(other)
                        stack.append(other)
        output.append([found[key] for key in sorted(found)])
    return sorted(output, key=lambda group: group[0]["edge_id"])


@dataclass(frozen=True)
class DP:
    objective: tuple[int, int, int]
    count: int
    union: frozenset[str]
    intersection: frozenset[str]
    representative: tuple[str, ...]


def solve(group: Sequence[dict[str, Any]]) -> DP:
    outflows = sorted({edge["outflow_txn_uid"] for edge in group})
    by_out = {
        uid: [edge for edge in group if edge["outflow_txn_uid"] == uid]
        for uid in outflows
    }

    @lru_cache(maxsize=None)
    def visit(index: int, used: frozenset[str]) -> DP:
        if index == len(outflows):
            return DP((0, 0, 0), 1, frozenset(), frozenset(), ())
        values = [visit(index + 1, used)]
        for edge in by_out[outflows[index]]:
            nodes = edge_nodes(edge)
            if nodes & used:
                continue
            suffix = visit(index + 1, used | nodes)
            cost = (
                -1,
                edge["time_delta_ms"],
                int(edge["evidence_grade"] == "SCHEDULE_SUPPORTED_FEE_CANDIDATE"),
            )
            edge_set = frozenset({edge["edge_id"]})
            values.append(
                DP(
                    tuple(a + b for a, b in zip(cost, suffix.objective)),
                    suffix.count,
                    suffix.union | edge_set,
                    suffix.intersection | edge_set,
                    tuple(sorted((*suffix.representative, edge["edge_id"]))),
                )
            )
        best = min(value.objective for value in values)
        winners = [value for value in values if value.objective == best]
        union = frozenset().union(*(value.union for value in winners))
        intersection = winners[0].intersection
        for winner in winners[1:]:
            intersection &= winner.intersection
        return DP(
            best,
            sum(value.count for value in winners),
            union,
            intersection,
            min(value.representative for value in winners),
        )

    return visit(0, frozenset())


def expected_classification(
    run_id: str, txs: Sequence[dict[str, Any]], edges: list[dict[str, Any]]
) -> dict[str, Any]:
    component_docs: list[dict[str, Any]] = []
    forced_all: set[str] = set()
    graph_nodes: set[str] = set()
    for group in components(edges):
        nodes = frozenset().union(*(edge_nodes(edge) for edge in group))
        graph_nodes |= nodes
        value = solve(group)
        forced_all |= value.intersection
        nonforced = value.union - value.intersection
        ambiguous = sorted(
            frozenset().union(
                *(edge_nodes(edge) for edge in group if edge["edge_id"] in nonforced)
            )
            if nonforced
            else frozenset()
        )
        selectable = (
            frozenset().union(
                *(edge_nodes(edge) for edge in group if edge["edge_id"] in value.union)
            )
            if value.union
            else frozenset()
        )
        component_id = digest(group)
        exact = len(nodes) <= 8
        component_docs.append(
            {
                "run_id": run_id,
                "component_id": component_id,
                "forced_edge_ids": sorted(value.intersection),
                "ambiguous_txn_uids": ambiguous,
                "unmatched_txn_uids": sorted(nodes - selectable),
                "has_alternative_optimum": value.count > 1,
                "alternative_optimum_count": value.count if exact else None,
                "alternative_optimum_count_exact": exact,
                "forced_pair_count": len(value.intersection),
                "residual_unmatched_count": len(nodes - selectable),
            }
        )
    forced_edges = [edge for edge in edges if edge["edge_id"] in forced_all]
    unmatched = sorted(tx["txn_uid"] for tx in txs if tx["txn_uid"] not in graph_nodes)
    return {
        "schema_version": "2.0.0",
        "run_id": run_id,
        "forced_edges": forced_edges,
        "components": sorted(component_docs, key=lambda item: item["component_id"]),
        "globally_unmatched_txn_uids": unmatched,
        "shadow_only": True,
        "affects_reporting": False,
    }


def verify_dlp(docs: Mapping[str, Any]) -> None:
    forbidden_key = re.compile(
        r"(?:^|_)(?:raw_text|raw_value|memo|holder_name|person_name|file_path|secret|password|account_number)(?:$|_)",
        re.I,
    )
    account = re.compile(r"(?<![A-Za-z0-9])(?:[0-9０-９][ -]?){8,20}(?![A-Za-z0-9])")
    home = re.compile(r"(?:/Users/|/home/|[A-Za-z]:\\\\Users\\\\)")
    secret = re.compile(
        r"(?:bearer\s+[A-Za-z0-9._~-]+|api[_-]?key|private[_-]?key)", re.I
    )
    email = re.compile(r"(?i)(?<![A-Z0-9._%+-])[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}(?![A-Z0-9.-])")
    allowed = re.compile(r"^[A-Za-z0-9._:+/@=-]{0,256}$")
    machine_identifier = re.compile(
        r"^(?:[0-9a-f]{32}|[0-9a-f]{40}|[0-9a-f]{64}|"
        r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}|"
        r"[0-9]{4}-[0-9]{2}-[0-9]{2}(?:T[0-9:.+-]+Z?)?)$"
    )
    adapter_header_keys = {
        "source_account",
        "bank_code",
        "booking_date",
        "withdrawal",
        "deposit",
        "reference",
        "counter_account",
        "fee_type",
        "product_code",
        "channel",
        "allowed_date_formats",
    }
    count = 0
    protected_machine_keys = re.compile(
        r"(?:digest|token|signature|sha256|nonce|oid|uuid|_id)$", re.I
    )

    def scan_text(text: str, key: str, depth: int = 0) -> None:
        if protected_machine_keys.search(key):
            return
        if machine_identifier.fullmatch(text) and not re.fullmatch(
            r"[0-9a-f]{32,64}", text
        ):
            return
        if home.search(text) or secret.search(text) or email.search(text) or account.search(text):
            block("BLOCK_DLP")
        if depth >= 2:
            return
        decoded: list[bytes] = []
        if re.fullmatch(r"[0-9A-Fa-f]{8,512}", text) and len(text) % 2 == 0:
            try:
                decoded.append(bytes.fromhex(text))
            except ValueError:
                pass
        if re.fullmatch(r"[A-Za-z0-9_-]{8,684}={0,2}", text):
            try:
                padded = text + "=" * (-len(text) % 4)
                decoded.append(base64.b64decode(padded, altchars=b"-_", validate=True))
            except (ValueError, TypeError):
                pass
        for raw_value in decoded:
            try:
                nested = raw_value.decode("utf-8")
            except UnicodeDecodeError:
                continue
            if nested != text:
                scan_text(nested, key, depth + 1)

    def visit(value: Any, key: str = "") -> None:
        nonlocal count
        if forbidden_key.search(key):
            block("BLOCK_DLP")
        if isinstance(value, dict):
            for child_key, child in value.items():
                visit(child, child_key)
        elif isinstance(value, list):
            for child in value:
                visit(child, key)
        elif isinstance(value, str):
            count += 1
            scan_text(value, key)
            if machine_identifier.fullmatch(value):
                return
            if key in adapter_header_keys and len(value.encode("utf-8")) <= 96:
                return
            if not allowed.fullmatch(value):
                block("BLOCK_DLP")
        elif value is not None and type(value) not in {int, bool}:
            block("BLOCK_DLP")

    scanned = {
        name: docs[name] for name in JSON_FILES - {"dlp_receipt.json", "manifest.json"}
    }
    for document in scanned.values():
        visit(document)
    receipt = docs["dlp_receipt.json"]
    if (
        receipt.get("files_scanned") != len(scanned)
        or receipt.get("values_scanned") != count
        or receipt.get("leak_count") != 0
        or receipt.get("closed_world_pass") is not True
    ):
        block("BLOCK_DLP")


def verify(
    root: Path,
    trust_path: Path,
    source_fd: int,
    source_suffix: str,
    key_material_fd: int,
    dictionary_path: Path,
) -> dict[str, Any]:
    raw = read_files(root)
    docs: dict[str, Any] = {}
    for name in JSON_FILES:
        docs[name] = strict_load(raw[name])
        if jcs(docs[name]) != raw[name]:
            block("BLOCK_CANONICAL_JSON")
    verify_hashes(raw, docs)
    run, txs, expected = verify_bindings(docs)
    if source_suffix != ".csv":
        # XLS/XLSX A4 remains fail-closed until formula, hidden-sheet and
        # relationship inspection is implemented in both compilers.
        block("BLOCK_UNSUPPORTED_SOURCE_FORMAT")
    verify_source_snapshot(source_fd, source_suffix, docs["input_receipt.json"])
    material = _key_material(key_material_fd, run["tenant_id"])
    dictionary = _dictionary(dictionary_path, run["dictionary_digest"])
    frame = read_source_frame(source_fd, source_suffix)
    independently_compiled = independently_compile_source(
        frame,
        docs["input_receipt.json"],
        run,
        docs["account_snapshot_receipt.json"]["accounts"],
        material,
        dictionary,
    )
    if independently_compiled != txs:
        block("BLOCK_SOURCE_SEMANTIC_MISMATCH")
    trust = load_trust(trust_path)
    graph = docs["graph_observation.json"]
    policy = verify_policy(
        docs["policy_receipt.json"], graph.get("policy_payload"), trust, expected
    )
    if docs["policy_receipt.json"]["policy_digest"] != run["policy_digest"]:
        block("BLOCK_BINDING")
    rebuilt, pair_checks, max_bucket_size = rebuild_edges(txs, policy)
    observed = graph
    expected_graph_keys = {
        "schema_version",
        "run_id",
        "nonce_digest",
        "tenant_id",
        "objective",
        "policy_payload",
        "candidate_pair_checks",
        "max_candidate_bucket_size",
        "edges",
    }
    if (
        set(observed) != expected_graph_keys
        or observed.get("schema_version") != "2.1.0"
        or observed.get("objective")
        != [
            "MAX_MATCHED_PRINCIPALS",
            "MIN_TIME_DISTANCE",
            "MIN_FEE_PENALTY",
            "ORDERED_EDGE_ID_VECTOR",
        ]
        or observed.get("candidate_pair_checks") != pair_checks
        or observed.get("max_candidate_bucket_size") != max_bucket_size
        or observed.get("edges") != rebuilt
    ):
        block("BLOCK_GRAPH")
    expected_result = expected_classification(run["run_id"], txs, rebuilt)
    if docs["classification_receipt.json"] != expected_result:
        block("BLOCK_OPTIMUM")
    invariants = docs["runtime_invariants.json"]
    exact_invariants = {
        "run_id": run["run_id"],
        "nonce_digest": expected["run_nonce_digest"],
        "shadow_only": True,
        "product_mutation_count": 0,
        "journal_auto_post_allowed": False,
        "affects_reporting": False,
        "runtime_activation_allowed": False,
        "observer_product_bytes_equal": True,
        "terminal_count": 1,
    }
    if invariants != exact_invariants:
        block("BLOCK_INVARIANT")
    verify_dlp(docs)
    resources_root = Path(__file__).resolve().parents[2]
    closure_files: dict[str, str] = {}
    for relative in CODE_FILES:
        target = resources_root / relative
        if not target.is_file() or target.is_symlink():
            block("BLOCK_CODE_CLOSURE")
        closure_files[relative] = hashlib.sha256(target.read_bytes()).hexdigest()
    code_closure_digest = digest(closure_files)
    verified_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    receipt = {
        "schema_version": "butler.box5.a4.verification_receipt.v3.1",
        "contract_id": "BUTLER-BOX5-A4-V3.1-CANONICAL-DIRECTIVE",
        "run_id": run["run_id"],
        "nonce": run["nonce"].lower(),
        "decision": "PASS",
        "reason_codes": [],
        "source_sha256": docs["input_receipt.json"]["source_file_sha256"],
        "ordered_row_root": docs["input_receipt.json"]["row_closure"]["ordered_row_root"],
        "compiled_manifest_digest": digest(independently_compiled),
        "graph_digest": digest(graph),
        "evidence_manifest_digest": hashlib.sha256(raw["manifest.json"]).hexdigest(),
        "policy_digest": run["policy_digest"],
        "adapter_digest": run["adapter_digest"],
        "dictionary_digest": run["dictionary_digest"],
        "registry_digest": run["registry_digest"],
        "code_tree_oid": run["code_tree_oid"],
        "code_closure_digest": code_closure_digest,
        "verifier_id": "BUTLER_A4_ISOLATED_RAW_COMPILER_V3.1",
        "signer_key_id": f"{material['key_id']}.a4-verifier-v31",
        "verified_at_utc": verified_at,
    }
    private = Ed25519PrivateKey.from_private_bytes(material["verification_signing_seed_b64"])
    signature = private.sign(jcs(receipt))
    receipt["signature"] = base64.urlsafe_b64encode(signature).decode("ascii").rstrip("=")
    return receipt


def main() -> int:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--evidence", required=True)
    parser.add_argument("--trust-policy", required=True)
    parser.add_argument("--source-fd", type=int)
    parser.add_argument("--source-suffix")
    parser.add_argument("--key-material-fd", type=int)
    parser.add_argument("--dictionary", required=True)
    try:
        args = parser.parse_args()
        if args.source_fd is None or args.source_suffix is None or args.key_material_fd is None:
            block("BLOCK_INPUT_CLOSURE")
        receipt = verify(
            Path(args.evidence),
            Path(args.trust_policy),
            args.source_fd,
            args.source_suffix,
            args.key_material_fd,
            Path(args.dictionary),
        )
    except Block as exc:
        print("A4_VERIFY_PASS=0")
        print(f"ERROR_CODE={exc}")
        return 1
    except Exception:
        print("A4_VERIFY_PASS=0")
        print("ERROR_CODE=BLOCK_INTERNAL")
        return 1
    print("A4_VERIFY_PASS=1")
    print("ERROR_CODE=NONE")
    print(
        "A4_VERIFICATION_RECEIPT_B64="
        + base64.urlsafe_b64encode(jcs(receipt)).decode("ascii").rstrip("=")
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
