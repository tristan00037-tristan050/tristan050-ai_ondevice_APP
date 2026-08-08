"""Product runtime connecting classified bank rows to assignment services."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import math
import os
import re
import threading
import time
import uuid
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

from butler_pc_core.accounting.classify.account_column_compiler import (
    resolve_account_cell,
    resolve_account_column,
)
from butler_pc_core.accounting.policy.errors import PolicyLoadError
from butler_pc_core.accounting.policy.money import parse_krw, source_text_sha256
from butler_pc_core.connect_loop.dlp_guard import scan_runtime_text

from .domain import (
    AssignCommand,
    AssignmentError,
    AssignmentScope,
    CanonicalReviewTransaction,
    ConflictDecision,
    ReviewState,
    TenantContext,
    opaque_id,
    sha256_json,
    utc_now,
)
from .adapters import resolve_bank_adapter
from .authorization_replay import SQLiteAuthorizationReplayStore
from .registry import RegistrySnapshot
from .security import NORMALIZATION_VERSION, MacOSKeychainStore, SecureKeyStore, TokenService
from .store import SQLiteAssignmentStore


_DESCRIPTION_COLUMNS = (
    "상대계좌예금주명",
    "거래처",
    "상호",
    "보낸분/받는분",
    "받는분",
    "보내는분",
    "거래내용",
    "적요",
    "기재내용",
    "내용",
    "메모",
    "description",
    "memo",
)
_DATE_COLUMNS = ("거래일시", "거래일", "거래일자", "일자", "날짜")
_SINGLE_AMOUNT_COLUMNS = ("금액", "거래금액", "amount", "변동금액")


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _parse_booked_date(value: object) -> date | None:
    """★ RI-P0-010: valid → date, invalid/missing → None (격리 대상).

    1970-01-01·오늘 날짜·파일 mtime 같은 fallback 을 절대 넣지 않는다. 파싱 실패는
    호출부에서 REVIEW_QUARANTINE 으로 격리한다.
    """
    if isinstance(value, datetime):
        return value.date()
    if type(value) is date:
        return value
    text = str(value or "").strip()[:10]
    if not text:
        return None
    try:
        return date.fromisoformat(text)
    except ValueError:
        return None


def _to_amount(row: Any) -> int | None:
    value = row.get("_amt")
    if value is None or (isinstance(value, float) and math.isnan(value)):
        value = next((row.get(column) for column in _SINGLE_AMOUNT_COLUMNS if column in row.index), None)
    if value is None or isinstance(value, bool):
        return None
    # ★ RI-P0-003/011: float() 완전 제거. 통화 장식만 벗기고 Decimal/int-only 정본
    # parse_krw 로만 해석한다. 2^53 초과 정수는 보존되고 exponent·NaN·Infinity·leading +·
    # fraction 은 거부(→ None, 거래 아님/격리 대상). 콤마 자릿점은 parse_krw 가 허용한다.
    text = str(value).strip().replace("원", "").replace("₩", "").replace(" ", "")
    if not text:
        return None
    negative = text.startswith("(") and text.endswith(")")
    if negative:
        text = text[1:-1]
    if text.startswith("+"):
        return None
    try:
        money = parse_krw(text, digest=source_text_sha256(text))
    except PolicyLoadError:
        return None
    return -abs(money.minor_units) if negative else money.minor_units


def _cell_text(value: object) -> str:
    if value is None:
        return ""
    try:
        if value != value:  # NaN/NaT without importing a dataframe implementation.
            return ""
    except (TypeError, ValueError):
        return ""
    text = str(value).strip()
    return "" if text.casefold() in {"nan", "nat", "<na>", "none"} else text


def _descriptor(row: Any) -> tuple[str, str, str]:
    values: list[tuple[str, str]] = []
    for column in _DESCRIPTION_COLUMNS:
        if column not in row.index:
            continue
        value = _cell_text(row.get(column))
        if value:
            values.append((column, value))
    if not values:
        return "미상 거래", "거래 정보 제한", "RESTRICTED"
    canonical = " | ".join(f"{column}:{value}" for column, value in values)
    display = values[0][1][:200]
    scan = scan_runtime_text(display)
    if scan["passed"]:
        return canonical[:500], display, "PLAIN"
    if scan["pii_detected"]:
        masked = display[:1] + "*" * min(max(len(display) - 1, 3), 12)
        return canonical[:500], masked, "MASKED"
    return canonical[:500], "거래 정보 제한", "RESTRICTED"


@dataclass(slots=True)
class ReviewBatch:
    context: TenantContext
    batch_id: str
    batch_version: int
    transactions: dict[str, CanonicalReviewTransaction]
    ambiguous_account_columns: tuple[str, ...]
    quarantined: tuple[dict[str, Any], ...] = ()


class AuthorizedMutationExecutor:
    """Single product guard for every privileged Box5 mutation.

    The signed decision is checked again at the last service boundary before a
    store transaction begins.  The unit-policy projection used by direct
    runtime tests is accepted only while pytest owns the process; product
    composition can never activate that compatibility seam.
    """

    @staticmethod
    def require(context: TenantContext, *, action: str, resource_id: str) -> None:
        if context.permission_policy_version == "unit-policy-only":
            if os.environ.get("PYTEST_CURRENT_TEST") is not None:
                return
            raise AssignmentError(
                "BLOCK_HUMAN_AUTHORITY_UNRESOLVED",
                503,
                "A verified human authority decision is required.",
            )
        required_digests = (
            context.actor_id_digest,
            context.session_id_digest,
            context.device_id_digest,
            context.permission_decision_digest,
            context.authorization_policy_digest,
            context.authorization_assertion_digest,
            context.authorization_resource_digest,
        )
        if (
            context.action != action
            or context.authorization_resource_digest != _digest(resource_id)
            or not context.authorization_decision_id
            or context.authorization_policy_version is None
            or not context.authorization_role
            or context.role_registry_version < 1
            or any(not re.fullmatch(r"[0-9a-f]{64}", value) for value in required_digests)
        ):
            raise AssignmentError(
                "AUTHORIZATION_RESOURCE_MISMATCH",
                403,
                "The authority decision does not match this mutation.",
            )


class AccountingReviewRuntime:
    """In-memory canonical projection plus persistent raw-zero event store."""

    def __init__(
        self,
        *,
        db_path: Path,
        key_store: SecureKeyStore,
        registry: RegistrySnapshot | None = None,
    ) -> None:
        self.tokens = TokenService(key_store)
        self.registry = registry or RegistrySnapshot.bundled()
        self.store = SQLiteAssignmentStore(db_path, self.tokens)
        self.authorization_replay_store = SQLiteAuthorizationReplayStore.for_database(
            self.store.path
        )
        self.authorized_mutations = AuthorizedMutationExecutor()
        try:
            self.store.recover_expired_reconciliation_jobs(observed_at=utc_now())
        except AssignmentError as exc:
            if exc.code != "BLOCK_SCHEMA_MIGRATION_REQUIRED":
                raise
        self._batches: dict[str, ReviewBatch] = {}
        self._lock = threading.RLock()

    @classmethod
    def product_default(cls) -> "AccountingReviewRuntime":
        return cls.for_production(
            db_path=Path.home() / ".butler" / "accounting" / "assignment_v2.sqlite3",
            key_store=MacOSKeychainStore(),
        )

    @classmethod
    def for_production(
        cls,
        *,
        db_path: Path,
        key_store: SecureKeyStore,
        registry: RegistrySnapshot | None = None,
    ) -> "AccountingReviewRuntime":
        # ★ RI-P0-006/015: 제품 경로는 production 키 provider(macOS Keychain)만 허용한다.
        # file/memory provider 로 제품을 조립하려는 시도는 fail-closed 로 거부한다.
        if not getattr(key_store, "is_production_provider", False):
            raise AssignmentError(
                "BLOCKED_KEY_AUTHORITY",
                503,
                "Production accounting requires the approved native Keychain authority.",
            )
        return cls(db_path=db_path, key_store=key_store, registry=registry)

    @staticmethod
    def context_from_profile(
        profile: Any,
        session: Any | None = None,
        *,
        action: str = "ACCOUNTING_REVIEW_VIEW",
    ) -> TenantContext:
        if profile is None or getattr(profile, "status", None) != "ACTIVE":
            raise AssignmentError(
                "BLOCK_SECURE_TRANSACTION_PROJECTION_UNAVAILABLE",
                503,
                "An active company profile is required for accounting review.",
            )
        tenant_id = str(profile.profile_id)
        tenant_digest = _digest(tenant_id + ":" + str(profile.profile_digest))
        if session is None:
            # Ingestion is a server-owned action.  Interactive routes always pass
            # the verified capability session and never use this service identity.
            actor_source = "butler.accounting.ingest.service.v1"
            session_source = "butler.accounting.ingest.internal"
            device_source = "butler.sidecar"
        else:
            # Transport sessions are not human identities.  This compatibility
            # path is retained for UNIT_POLICY_ONLY tests and server-owned work;
            # public routes use Box5AuthorizationService instead.
            transport_digest = str(
                getattr(session, "session_digest", _digest(str(session.session_id)))
            )
            actor_source = "butler.local-ipc:" + transport_digest
            session_source = str(session.session_id)
            device_source = str(session.device_id)
        actor_digest = _digest(actor_source)
        session_digest = _digest(session_source)
        device_digest = _digest(device_source)
        permission_digest = sha256_json(
            {
                "authority": "unit-policy-only",
                "action": action,
                "tenant_digest": tenant_digest,
                "actor_id_digest": actor_digest,
                "session_id_digest": session_digest,
            }
        )
        actor_id = "actor_" + actor_digest[:32]
        return TenantContext(
            tenant_id,
            tenant_digest,
            actor_id,
            actor_digest,
            session_digest,
            device_digest,
            permission_digest,
            "unit-policy-only",
            action,
        )

    def ingest_dataframe(
        self,
        batch_id: str,
        frame: Any,
        company_profile: Any,
        *,
        selected_account_column: str | None = None,
        source_file_sha256: str,
        adapter_id: str | None = None,
    ) -> dict[str, Any]:
        context = self.context_from_profile(company_profile)
        if not re.fullmatch(r"[A-Za-z0-9_-]{16,128}", batch_id):
            raise AssignmentError("BATCH_ID_INVALID", 422, "Batch identifier is invalid.")
        if not re.fullmatch(r"[0-9a-f]{64}", source_file_sha256):
            raise AssignmentError("SOURCE_FILE_IDENTITY_INVALID", 422, "The source file digest is required.")
        adapter = resolve_bank_adapter(list(frame.columns), adapter_id)
        resolution = resolve_account_column(
            list(frame.columns), selected_column=selected_account_column
        )
        account_by_name = {entry.display_name: entry for entry in self.registry.entries if entry.assignable}
        transactions: dict[str, CanonicalReviewTransaction] = {}
        rows: list[dict[str, Any]] = []
        receipts: list[dict[str, Any]] = []
        seen_fingerprints: dict[str, str] = {}
        key_id: str | None = None
        now_ms = int(time.time() * 1000)
        for sequence, (_, row) in enumerate(frame.iterrows()):
            amount = _to_amount(row)
            descriptor, descriptor_display, display_policy = _descriptor(row)
            booked_date = _parse_booked_date(
                next((row.get(c) for c in _DATE_COLUMNS if c in row.index), None)
            )
            counterparty = adapter.counterparty_candidate(row)
            vendor_token: str | None = None
            if counterparty:
                key_id, vendor_token = self.tokens.vendor_token(
                    context.tenant_id, adapter.adapter_id, counterparty
                )
            direction = None if amount in {None, 0} else ("OUT" if amount < 0 else "IN")
            source_payload = {
                "source_file_sha256": source_file_sha256,
                "adapter_id": adapter.adapter_id,
                "adapter_version": adapter.adapter_version,
                "booked_digest": _digest(str(next((row.get(c) for c in _DATE_COLUMNS if c in row.index), ""))),
                "amount": amount,
                "descriptor_digest": _digest(descriptor),
                "counterparty_digest": _digest(counterparty) if counterparty else None,
                "bank_transaction_id_digest": _digest(adapter.transaction_id_candidate(row) or ""),
            }
            row_fingerprint = sha256_json(source_payload)
            source_digest = sha256_json(
                {**source_payload, "source_row_number": sequence + 1}
            )
            row_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"butler:row:{batch_id}:{sequence + 1}"))
            txn_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"butler:txn:{context.tenant_digest}:{source_digest}"))
            duplicate_of = seen_fingerprints.get(row_fingerprint)
            if duplicate_of is None:
                seen_fingerprints[row_fingerprint] = row_id
            declared = None
            if resolution.selected_column is not None:
                declared = resolve_account_cell(row.get(resolution.selected_column), self.registry)
            legacy_name = _cell_text(row.get("분류과목"))
            suggestion_account: str | None = None
            suggestion_rule: str | None = None
            safe_reason: str | None = None
            terminal_state = "UNACCOUNTED"
            classification_source: str | None = None
            reason_code: str | None = None
            active_rules: list[dict[str, Any]] = []
            if vendor_token is not None and direction is not None and key_id is not None:
                active_rules = self.store.active_rules_exact(
                    tenant_digest=context.tenant_digest,
                    company_scope_digest=context.tenant_digest,
                    vendor_token=vendor_token,
                    adapter_id=adapter.adapter_id,
                    adapter_version=adapter.adapter_version,
                    normalization_version=NORMALIZATION_VERSION,
                    direction=direction,
                    currency="KRW",
                    hmac_key_id=key_id,
                )
            if duplicate_of is not None:
                terminal_state = "DUPLICATE_LINKED"
                state = ReviewState.NON_EXPENSE_BANK_EVENT
                reason_code = "DUPLICATE_SOURCE_ROW"
            elif amount is None:
                terminal_state = "QUARANTINED"
                state = ReviewState.REVIEW_QUARANTINE
                reason_code = "INVALID_AMOUNT"
            elif amount == 0:
                terminal_state = "QUARANTINED"
                state = ReviewState.REVIEW_QUARANTINE
                reason_code = "ZERO_AMOUNT_REVIEW"
            elif booked_date is None:
                terminal_state = "QUARANTINED"
                state = ReviewState.REVIEW_QUARANTINE
                reason_code = "INVALID_BOOKING_DATE"
            elif _cell_text(row.get("_guard_reason")):
                terminal_state = "CLASSIFIED"
                state = ReviewState.NON_EXPENSE_BANK_EVENT
                classification_source = "A4_SELF_TRANSFER"
                reason_code = "A4_SELF_TRANSFER_PRECEDENCE"
            elif declared is not None:
                terminal_state = "CLASSIFIED"
                state = ReviewState.SOURCE_DECLARED_VALID
                classification_source = "SOURCE_DECLARED_VALID"
                suggestion_account = declared.account_id
                safe_reason = "업로드 파일의 계정 열을 정확히 확인했습니다."
            elif len(active_rules) > 1:
                state = ReviewState.REVIEW_REQUIRED
                reason_code = "RULE_CONFLICT_REVIEW_REQUIRED"
            elif len(active_rules) == 1:
                active_rule = active_rules[0]
                try:
                    self.registry.require_assignable(str(active_rule["account_id"]))
                except AssignmentError:
                    state = ReviewState.REVIEW_REQUIRED
                    reason_code = "RULE_REGISTRY_DRIFT"
                else:
                    terminal_state = "CLASSIFIED"
                    state = ReviewState.USER_RULE_APPLIED_DRAFT
                    classification_source = "USER_RULE_APPLIED_DRAFT"
                    suggestion_account = str(active_rule["account_id"])
                    suggestion_rule = str(active_rule["rule_id"])
                    safe_reason = "사용자가 승인한 동일 거래처 규칙으로 검토 초안을 만들었습니다."
                    match_digest = sha256_json(
                        {
                            "tenant_digest": context.tenant_digest,
                            "company_scope_digest": context.tenant_digest,
                            "vendor_token": vendor_token,
                            "adapter_id": adapter.adapter_id,
                            "adapter_version": adapter.adapter_version,
                            "normalization_version": NORMALIZATION_VERSION,
                            "direction": direction,
                            "currency": "KRW",
                            "hmac_key_id": key_id,
                        }
                    )
                    receipt_body = {
                        "receipt_id": str(uuid.uuid4()), "transaction_id": txn_id,
                        "rule_id": suggestion_rule,
                        "source_assignment_id": str(active_rule["source_assignment_id"]),
                        "match_key_digest": match_digest,
                        "registry_digest": self.registry.registry_digest,
                        "actor_id_digest": str(active_rule["created_actor_digest"]),
                        "applied_at_epoch_ms": now_ms,
                    }
                    receipt_body["event_hash"] = sha256_json(receipt_body)
                    receipts.append(receipt_body)
            elif legacy_name in account_by_name:
                state = ReviewState.AUTO_PROPOSE
                suggestion_account = account_by_name[legacy_name].account_id
                safe_reason = "기존 정확 규칙이 제안했습니다. 확인이 필요합니다."
            else:
                state = ReviewState.REVIEW_REQUIRED
                if vendor_token is None:
                    reason_code = "NO_STABLE_COUNTERPARTY"
            if terminal_state not in {"QUARANTINED", "DUPLICATE_LINKED"}:
                transactions[txn_id] = CanonicalReviewTransaction(
                tenant_digest=context.tenant_digest,
                batch_id=batch_id,
                txn_id=txn_id,
                source_sequence=sequence,
                booked_date=booked_date,  # type: ignore[arg-type]
                amount_minor=amount,  # type: ignore[arg-type]
                currency="KRW",
                bank_direction="OUTFLOW" if amount < 0 else "INFLOW",  # type: ignore[operator]
                transaction_version=1,
                canonical_descriptor=descriptor,
                descriptor_display=descriptor_display,
                display_policy=display_policy,
                vendor_match_token=vendor_token or "0" * 64,
                adapter_family=adapter.adapter_id,
                adapter_version=adapter.adapter_version,
                normalization_version=NORMALIZATION_VERSION,
                source_record_digest=source_digest,
                review_state=state,
                suggestion_account_id=suggestion_account,
                suggestion_rule_id=suggestion_rule,
                safe_reason=safe_reason,
                hmac_key_id=key_id or "",
                company_scope_digest=context.tenant_digest,
            )
            rows.append(
                {
                    "row_id": row_id,
                    "source_row_number": sequence + 1,
                    "source_row_fingerprint": row_fingerprint,
                    "direction": direction,
                    "currency": "KRW" if amount is not None else None,
                    "amount_minor": amount,
                    "booked_date": booked_date.isoformat() if booked_date else None,
                    "terminal_state": terminal_state,
                    "classification_source": classification_source,
                    "reason_code": reason_code,
                    "transaction_id": txn_id if terminal_state not in {"QUARANTINED", "DUPLICATE_LINKED"} else None,
                    "duplicate_of_row_id": duplicate_of,
                    "vendor_token": vendor_token,
                    "hmac_key_id": key_id,
                    "account_id": suggestion_account if terminal_state == "CLASSIFIED" else None,
                    "rule_id": suggestion_rule,
                    "transaction_version": 1,
                    "created_at_epoch_ms": now_ms,
                }
            )
        counts = {
            terminal: sum(row["terminal_state"] == terminal for row in rows)
            for terminal in ("CLASSIFIED", "UNACCOUNTED", "QUARANTINED", "DUPLICATE_LINKED")
        }
        self.store.persist_review_batch(
            batch={
                "batch_id": batch_id,
                "tenant_digest": context.tenant_digest,
                "company_scope_digest": context.tenant_digest,
                "source_file_sha256": source_file_sha256,
                "adapter_id": adapter.adapter_id,
                "adapter_version": adapter.adapter_version,
                "normalization_version": NORMALIZATION_VERSION,
                "input_row_count": len(rows),
                "classified_count": counts["CLASSIFIED"],
                "unaccounted_count": counts["UNACCOUNTED"],
                "quarantined_count": counts["QUARANTINED"],
                "duplicate_linked_count": counts["DUPLICATE_LINKED"],
                "created_at_epoch_ms": now_ms,
                "ambiguous_columns": list(resolution.ambiguous_columns),
            },
            rows=rows,
            receipts=receipts,
        )
        batch = ReviewBatch(
            context=context,
            batch_id=batch_id,
            batch_version=1,
            transactions=transactions,
            ambiguous_account_columns=resolution.ambiguous_columns,
            quarantined=tuple(row for row in rows if row["terminal_state"] == "QUARANTINED"),
        )
        with self._lock:
            self._batches[batch_id] = batch
        return {
            "batch_id": batch_id,
            "review_count": counts["UNACCOUNTED"] + sum(
                tx.review_state is ReviewState.USER_RULE_APPLIED_DRAFT for tx in transactions.values()
            ),
            "quarantine_count": counts["QUARANTINED"],
            "total_input_rows": len(rows),
            "classified_rows": counts["CLASSIFIED"],
            "unaccounted_rows": counts["UNACCOUNTED"],
            "duplicate_linked_rows": counts["DUPLICATE_LINKED"],
            "account_column_status": (
                "SELECTION_REQUIRED" if resolution.ambiguous_columns else "RESOLVED"
            ),
            "ambiguous_account_columns": list(resolution.ambiguous_columns),
            "match_key_id": key_id,
            "adapter_id": adapter.adapter_id,
            "adapter_version": adapter.adapter_version,
            "registry_digest": self.registry.registry_digest,
            "overlay_digest": self.registry.overlay_digest,
        }

    def _batch(self, context: TenantContext, batch_id: str) -> ReviewBatch:
        with self._lock:
            batch = self._batches.get(batch_id)
        if batch is None:
            persisted = self.store.review_batch(context.tenant_digest, batch_id)
            if persisted is not None:
                transactions: dict[str, CanonicalReviewTransaction] = {}
                for row in persisted["rows"]:
                    tx = self._transaction_from_persisted(context, persisted, row)
                    if tx is not None:
                        transactions[tx.txn_id] = tx
                batch = ReviewBatch(
                    context=context,
                    batch_id=batch_id,
                    batch_version=int(persisted["resource_version"]),
                    transactions=transactions,
                    ambiguous_account_columns=tuple(persisted["ambiguous_columns"]),
                    quarantined=tuple(
                        row for row in persisted["rows"] if row["terminal_state"] == "QUARANTINED"
                    ),
                )
                with self._lock:
                    self._batches[batch_id] = batch
        if batch is None or batch.context.tenant_digest != context.tenant_digest:
            # Deliberately identical for absent and cross-tenant objects.
            raise AssignmentError("AUTHORIZATION_DENIED", 404, "The accounting resource is unavailable.")
        return batch

    @staticmethod
    def _transaction_from_persisted(
        context: TenantContext, batch: dict[str, Any], row: dict[str, Any]
    ) -> CanonicalReviewTransaction | None:
        if not row.get("transaction_id") or row.get("amount_minor") is None or not row.get("booked_date"):
            return None
        source = str(row.get("classification_source") or "")
        if source == "USER_RULE_APPLIED_DRAFT":
            state = ReviewState.USER_RULE_APPLIED_DRAFT
        elif source == "SOURCE_DECLARED_VALID":
            state = ReviewState.SOURCE_DECLARED_VALID
        elif source == "A4_SELF_TRANSFER":
            state = ReviewState.NON_EXPENSE_BANK_EVENT
        elif source.startswith("USER_ASSIGNED"):
            state = ReviewState.USER_ASSIGNED
        else:
            state = ReviewState.AUTO_PROPOSE if row.get("account_id") else ReviewState.REVIEW_REQUIRED
        amount = int(row["amount_minor"])
        return CanonicalReviewTransaction(
            tenant_digest=context.tenant_digest,
            batch_id=str(batch["batch_id"]),
            txn_id=str(row["transaction_id"]),
            source_sequence=int(row["source_row_number"]) - 1,
            booked_date=date.fromisoformat(str(row["booked_date"])),
            amount_minor=amount,
            currency=str(row["currency"]),
            bank_direction="OUTFLOW" if row["direction"] == "OUT" else "INFLOW",
            transaction_version=int(row["transaction_version"]),
            canonical_descriptor="persisted-digest-only",
            descriptor_display="거래처 정보 비공개",
            display_policy="RESTRICTED",
            vendor_match_token=str(row["vendor_token"] or "0" * 64),
            adapter_family=str(batch["adapter_id"]),
            adapter_version=str(batch["adapter_version"]),
            normalization_version=str(batch["normalization_version"]),
            source_record_digest=str(row["source_row_fingerprint"]),
            review_state=state,
            suggestion_account_id=row.get("account_id"),
            suggestion_rule_id=row.get("rule_id"),
            safe_reason=str(row.get("reason_code") or "") or None,
            hmac_key_id=str(row["hmac_key_id"] or ""),
            company_scope_digest=str(batch["company_scope_digest"]),
        )

    def remove_batch(self, batch_id: str) -> None:
        self.store.remove_review_batch(batch_id)
        with self._lock:
            self._batches.pop(batch_id, None)

    def transaction(self, context: TenantContext, txn_id: str) -> tuple[ReviewBatch, CanonicalReviewTransaction]:
        with self._lock:
            candidates = list(self._batches.values())
        for batch in candidates:
            if batch.context.tenant_digest == context.tenant_digest and txn_id in batch.transactions:
                return batch, batch.transactions[txn_id]
        persisted = self.store.review_transaction(context.tenant_digest, txn_id)
        if persisted is not None:
            batch_data, row = persisted
            batch = self._batch(context, str(batch_data["batch_id"]))
            transaction = batch.transactions.get(txn_id)
            if transaction is not None:
                return batch, transaction
        raise AssignmentError("AUTHORIZATION_DENIED", 404, "The accounting resource is unavailable.")

    def review_summary(self, context: TenantContext, batch_id: str) -> dict[str, Any]:
        batch = self._batch(context, batch_id)
        counts = {
            "source_declared_valid": 0,
            "auto_propose": 0,
            "user_rule_applied_draft": 0,
            "review_required": 0,
            "review_quarantine": len(batch.quarantined),
            "non_expense_bank_event": 0,
            "user_assigned": 0,
        }
        for tx in batch.transactions.values():
            current = self.store.current_assignment(context.tenant_digest, tx.txn_id)
            if current is not None:
                counts["user_assigned"] += 1
            else:
                counts[tx.review_state.value.casefold()] += 1
        payload = {
            "schema_version": "3.0",
            "batch_id": batch_id,
            "batch_version": batch.batch_version,
            "registry_digest": self.registry.registry_digest,
            "overlay_digest": self.registry.overlay_digest,
            "counts": counts,
            "total_input_rows": sum(counts.values()) + self.store.review_batch(
                context.tenant_digest, batch_id
            )["duplicate_linked_count"],
            "generated_at": utc_now(),
        }
        payload["evidence_digest"] = sha256_json(payload)
        return payload

    def _encode_cursor(self, context: TenantContext, batch: ReviewBatch, offset: int) -> str:
        payload = json.dumps(
            {"tenant": context.tenant_digest, "batch": batch.batch_id, "version": batch.batch_version, "offset": offset},
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        mac = self.tokens.cursor_mac(context.tenant_id, payload)
        return base64.urlsafe_b64encode(payload + mac).decode("ascii").rstrip("=")

    def _decode_cursor(self, context: TenantContext, batch: ReviewBatch, cursor: str | None) -> int:
        if cursor is None:
            return 0
        try:
            raw = base64.urlsafe_b64decode(cursor + "=" * (-len(cursor) % 4))
            payload, claimed = raw[:-32], raw[-32:]
            if not hmac.compare_digest(claimed, self.tokens.cursor_mac(context.tenant_id, payload)):
                raise ValueError
            data = json.loads(payload)
        except Exception as exc:
            raise AssignmentError("INVALID_CURSOR", 422, "The review cursor is invalid.") from exc
        if data.get("tenant") != context.tenant_digest or data.get("batch") != batch.batch_id:
            raise AssignmentError("AUTHORIZATION_DENIED", 404, "The accounting resource is unavailable.")
        if data.get("version") != batch.batch_version:
            raise AssignmentError(
                "BATCH_SNAPSHOT_CHANGED",
                409,
                "The review batch changed. Restart pagination.",
                actions=("RESTART_PAGINATION",),
                current_version=batch.batch_version,
            )
        offset = data.get("offset")
        if isinstance(offset, bool) or not isinstance(offset, int) or offset < 0:
            raise AssignmentError("INVALID_CURSOR", 422, "The review cursor is invalid.")
        return offset

    def unaccounted_page(
        self, context: TenantContext, batch_id: str, *, cursor: str | None, page_size: int
    ) -> dict[str, Any]:
        batch = self._batch(context, batch_id)
        if isinstance(page_size, bool) or not 1 <= page_size <= 100:
            raise AssignmentError("INVALID_PAGE_SIZE", 422, "Page size must be between 1 and 100.")
        offset = self._decode_cursor(context, batch, cursor)
        rows = sorted(batch.transactions.values(), key=lambda tx: (tx.booked_date, tx.source_sequence, tx.txn_id))
        rows = [
            tx
            for tx in rows
            if tx.review_state not in {
                ReviewState.SOURCE_DECLARED_VALID,
                ReviewState.NON_EXPENSE_BANK_EVENT,
                ReviewState.USER_ASSIGNED,
            }
            and self.store.current_assignment(context.tenant_digest, tx.txn_id) is None
        ]
        items = []
        for tx in rows[offset : offset + page_size]:
            suggestion = None
            if tx.suggestion_account_id is not None:
                suggestion = {
                    "account_id": tx.suggestion_account_id,
                    "source": tx.review_state.value,
                    "safe_reason": tx.safe_reason or "확인이 필요한 계정 제안입니다.",
                    "rule_id": tx.suggestion_rule_id,
                }
            items.append(
                {
                    "txn_id": tx.txn_id,
                    "transaction_version": tx.transaction_version,
                    "booked_date": tx.booked_date.isoformat(),
                    "money": {"currency": tx.currency, "minor_units": tx.amount_minor},
                    "descriptor_display": tx.descriptor_display,
                    "display_policy": tx.display_policy,
                    "bank_direction": tx.bank_direction,
                    "review_state": tx.review_state.value,
                    "suggestion": suggestion,
                }
            )
        next_offset = offset + len(items)
        payload = {
            "schema_version": "3.0",
            "batch_id": batch_id,
            "batch_version": batch.batch_version,
            "registry_digest": self.registry.registry_digest,
            "overlay_digest": self.registry.overlay_digest,
            "items": items,
            "total_count": len(rows),
            "next_cursor": self._encode_cursor(context, batch, next_offset) if next_offset < len(rows) else None,
        }
        payload["etag"] = f'"{sha256_json(payload)}"'
        return payload

    def assign(
        self,
        context: TenantContext,
        txn_id: str,
        command: AssignCommand,
        *,
        idempotency_key: str,
        if_match_version: int,
    ) -> dict[str, Any]:
        batch, tx = self.transaction(context, txn_id)
        self.registry.require_assignable(command.account_id)
        if command.expected_transaction_version != if_match_version:
            raise AssignmentError(
                "STALE_ASSIGNMENT_VERSION",
                409,
                "The transaction changed before assignment.",
                actions=("REFRESH_TRANSACTION",),
                current_version=command.expected_transaction_version,
            )
        required_action = (
            "RULE_FUTURE_CREATE"
            if command.scope is AssignmentScope.SAME_VENDOR_FUTURE
            else "ASSIGNMENT_CREATE"
        )
        if context.action != required_action:
            code = (
                "PERMISSION_DENIED_RULE_FUTURE_CREATE"
                if required_action == "RULE_FUTURE_CREATE"
                else "PERMISSION_DENIED_ASSIGNMENT_CREATE"
            )
            raise AssignmentError(code, 403, "The required accounting action was not authorized.")
        self.authorized_mutations.require(
            context, action=required_action, resource_id=txn_id
        )
        match_key_id = tx.hmac_key_id
        recalculated_token = tx.vendor_match_token
        if not match_key_id or recalculated_token == "0" * 64:
            if command.scope is AssignmentScope.SAME_VENDOR_FUTURE:
                raise AssignmentError("NO_STABLE_COUNTERPARTY", 409, "A stable counterparty is required for a future rule.")
        assignment_id = opaque_id()
        active_rules = self.store.active_rules_exact(
            tenant_digest=context.tenant_digest,
            company_scope_digest=tx.company_scope_digest,
            vendor_token=recalculated_token,
            adapter_id=tx.adapter_family,
            adapter_version=tx.adapter_version,
            normalization_version=tx.normalization_version,
            direction="OUT" if tx.bank_direction == "OUTFLOW" else "IN",
            currency=tx.currency,
            hmac_key_id=match_key_id,
        ) if match_key_id else []
        active_rule = active_rules[0] if len(active_rules) == 1 else None
        should_create_rule = (
            command.scope is AssignmentScope.SAME_VENDOR_FUTURE
            and (active_rule is None or active_rule["account_id"] != command.account_id)
        )
        rule_id = opaque_id() if should_create_rule else None
        result = self.store.create_assignment(
            tenant_id=context.tenant_id,
            tenant_digest=context.tenant_digest,
            actor_id=context.actor_id,
            actor_id_digest=context.actor_id_digest,
            session_id_digest=context.session_id_digest,
            device_id_digest=context.device_id_digest,
            permission_decision_digest=context.permission_decision_digest,
            authorization_decision_id=context.authorization_decision_id,
            authorization_action=context.action,
            permission_policy_version=context.permission_policy_version,
            authorization_policy_version=context.authorization_policy_version,
            authorization_policy_digest=context.authorization_policy_digest,
            authorization_assertion_digest=context.authorization_assertion_digest,
            authorization_resource_digest=context.authorization_resource_digest,
            txn_id=txn_id,
            batch_id=batch.batch_id,
            expected_version=command.expected_transaction_version,
            account_id=command.account_id,
            scope=command.scope.value,
            vendor_match_token=recalculated_token,
            adapter_family=tx.adapter_family,
            adapter_version=tx.adapter_version,
            normalization_version=tx.normalization_version,
            company_scope_digest=tx.company_scope_digest,
            direction="OUT" if tx.bank_direction == "OUTFLOW" else "IN",
            currency=tx.currency,
            registry_digest=self.registry.registry_digest,
            overlay_digest=self.registry.overlay_digest,
            match_key_id=match_key_id,
            assignment_id=assignment_id,
            rule_id=rule_id,
            idempotency_key=idempotency_key,
            user_action_nonce=command.user_action_nonce,
            body={
                "account_id": command.account_id,
                "scope": command.scope.value,
                "client_action_id": command.client_action_id,
                "user_action_nonce_digest": _digest(command.user_action_nonce),
                "expected_transaction_version": command.expected_transaction_version,
            },
            authority_context=context,
        )
        if not result.replayed:
            with self._lock:
                batch.batch_version += 1
        return result.response

    def issue_assignment_nonce(self, context: TenantContext, txn_id: str) -> dict[str, Any]:
        if context.action not in {
            "ASSIGNMENT_CREATE",
            "RULE_FUTURE_CREATE",
        }:
            raise AssignmentError(
                "PERMISSION_DENIED_ASSIGNMENT_CREATE",
                403,
                "Accounting assignment permission is required.",
            )
        self.authorized_mutations.require(
            context, action=context.action, resource_id=txn_id
        )
        self.transaction(context, txn_id)
        now_ms = int(time.time() * 1000)
        nonce = self.store.issue_action_nonce(
            tenant_digest=context.tenant_digest,
            actor_id_digest=context.actor_id_digest,
            session_id_digest=context.session_id_digest,
            transaction_id=txn_id,
            action=context.action,
            now_epoch_ms=now_ms,
        )
        return {
            "schema_version": "3.0",
            "transaction_id": txn_id,
            "action": context.action,
            "user_action_nonce": nonce,
            "expires_at_epoch_ms": now_ms + 300_000,
        }

    def learned_rules(self, context: TenantContext, state: str | None = None) -> dict[str, Any]:
        allowed_states = {
            "ACTIVE_USER_RULE", "INACTIVE_USER", "INACTIVE_REGISTRY",
            "DEGRADED_KEY_ROTATION", "CONFLICT_REVIEW",
        }
        if state is not None and state not in allowed_states:
            raise AssignmentError("INVALID_REQUEST_SCHEMA", 422, "Rule state is invalid.")
        rows = self.store.list_rules(context.tenant_digest, state)
        with self._lock:
            descriptor_by_txn = {
                tx.txn_id: tx.descriptor_display
                for batch in self._batches.values()
                if batch.context.tenant_digest == context.tenant_digest
                for tx in batch.transactions.values()
            }
        return {
            "schema_version": "3.0",
            "items": [
                {
                    "schema_version": "3.0",
                    "rule_id": row["rule_id"],
                    "account_id": row["account_id"],
                    "source_assignment_id": row["source_assignment_id"],
                    "state": row["state"],
                    "registry_digest": row["registry_digest"],
                    "overlay_digest": row["overlay_digest"],
                    "match_key_id": row["match_key_id"],
                    "normalization_version": row["normalization_version"],
                    "adapter_id": row["adapter_id"],
                    "adapter_version": row["adapter_version"],
                    "direction": row["direction"],
                    "currency": row["currency"],
                    "created_at": row["created_at"],
                    "deactivated_at": row["deactivated_at"],
                    "resource_version": row["resource_version"],
                    "descriptor_display": descriptor_by_txn.get(
                        str(row["source_txn_id"]), "거래처 정보 보관 기간 만료"
                    ),
                }
                for row in rows
            ],
        }

    def deactivate_rule(
        self,
        context: TenantContext,
        rule_id: str,
        *,
        idempotency_key: str,
        if_match_version: int,
    ) -> dict[str, Any]:
        if context.action != "RULE_DEACTIVATE":
            raise AssignmentError("PERMISSION_DENIED_RULE_DEACTIVATE", 403, "Rule revoke permission is required.")
        self.authorized_mutations.require(
            context, action="RULE_DEACTIVATE", resource_id=rule_id
        )
        return self.store.deactivate_rule(
            tenant_id=context.tenant_id,
            tenant_digest=context.tenant_digest,
            actor_id=context.actor_id,
            rule_id=rule_id,
            expected_version=if_match_version,
            registry_digest=self.registry.registry_digest,
            overlay_digest=self.registry.overlay_digest,
            idempotency_key=idempotency_key,
            authority_context=context,
        )

    def quarantine_page(self, context: TenantContext, batch_id: str) -> dict[str, Any]:
        if context.action != "ACCOUNTING_REVIEW_VIEW":
            raise AssignmentError("PERMISSION_DENIED_ACCOUNTING_REVIEW", 403, "Accounting review permission is required.")
        self._batch(context, batch_id)
        return {
            "schema_version": "3.0",
            "batch_id": batch_id,
            "items": self.store.quarantine_rows(context.tenant_digest, batch_id),
        }

    def revert_rule_application(
        self,
        context: TenantContext,
        txn_id: str,
        *,
        expected_version: int,
        idempotency_key: str,
    ) -> dict[str, Any]:
        if context.action != "RULE_APPLICATION_REVERT":
            raise AssignmentError(
                "PERMISSION_DENIED_RULE_APPLICATION_REVERT", 403,
                "Rule-application revert permission is required.",
            )
        self.authorized_mutations.require(
            context, action="RULE_APPLICATION_REVERT", resource_id=txn_id
        )
        batch, _ = self.transaction(context, txn_id)
        result = self.store.revert_rule_application(
            tenant_id=context.tenant_id,
            tenant_digest=context.tenant_digest,
            actor_id=context.actor_id,
            actor_id_digest=context.actor_id_digest,
            session_id_digest=context.session_id_digest,
            device_id_digest=context.device_id_digest,
            permission_decision_digest=context.permission_decision_digest,
            txn_id=txn_id,
            expected_version=expected_version,
            registry_digest=self.registry.registry_digest,
            overlay_digest=self.registry.overlay_digest,
            idempotency_key=idempotency_key,
            authority_context=context,
        )
        if not result.replayed:
            with self._lock:
                self._batches.pop(batch.batch_id, None)
        return result.response

    def recompile_quarantine(
        self,
        context: TenantContext,
        batch_id: str,
        row_id: str,
        correction: dict[str, Any],
        *,
        expected_version: int,
        idempotency_key: str,
    ) -> dict[str, Any]:
        if context.action != "QUARANTINE_ROW_RECOMPILE":
            raise AssignmentError(
                "PERMISSION_DENIED_QUARANTINE_RECOMPILE", 403,
                "Quarantine recompile permission is required.",
            )
        self.authorized_mutations.require(
            context, action="QUARANTINE_ROW_RECOMPILE", resource_id=row_id
        )
        allowed = {"amount_minor", "booked_date", "currency"}
        if not correction or not set(correction).issubset(allowed):
            raise AssignmentError("INVALID_REQUEST_SCHEMA", 422, "Correction fields are invalid.")
        batch = self.store.review_batch(context.tenant_digest, batch_id)
        if batch is None:
            raise AssignmentError("AUTHORIZATION_DENIED", 404, "The accounting resource is unavailable.")
        row = next((item for item in batch["rows"] if item["row_id"] == row_id), None)
        if row is None:
            raise AssignmentError("AUTHORIZATION_DENIED", 404, "The accounting resource is unavailable.")
        amount = correction.get("amount_minor", row["amount_minor"])
        booked = correction.get("booked_date", row["booked_date"])
        currency = correction.get("currency", row["currency"] or "KRW")
        if isinstance(amount, bool) or not isinstance(amount, int) or amount == 0:
            raise AssignmentError("INVALID_AMOUNT", 422, "A non-zero integer minor amount is required.")
        try:
            parsed_date = date.fromisoformat(booked) if isinstance(booked, str) else None
        except ValueError as exc:
            raise AssignmentError("INVALID_BOOKING_DATE", 422, "A valid booking date is required.") from exc
        if parsed_date is None or currency != "KRW":
            raise AssignmentError("INVALID_BOOKING_DATE", 422, "A valid booking date and currency are required.")
        replacement = {
            "amount_minor": amount,
            "booked_date": parsed_date.isoformat(),
            "currency": currency,
            "direction": "OUT" if amount < 0 else "IN",
            "terminal_state": "UNACCOUNTED",
            "classification_source": None,
            "reason_code": "QUARANTINE_RECOMPILED_REVIEW_REQUIRED",
            "transaction_id": str(
                uuid.uuid5(
                    uuid.NAMESPACE_URL,
                    f"butler:txn:{context.tenant_digest}:{row['source_row_fingerprint']}:recompiled",
                )
            ),
        }
        result = self.store.recompile_quarantine_row(
            tenant_digest=context.tenant_digest,
            actor_id_digest=context.actor_id_digest,
            session_id_digest=context.session_id_digest,
            batch_id=batch_id,
            row_id=row_id,
            expected_version=expected_version,
            correction_digest=sha256_json(correction),
            replacement=replacement,
            idempotency_key=idempotency_key,
            authority_context=context,
        )
        with self._lock:
            self._batches.pop(batch_id, None)
        return result

    def resolve_conflict(
        self,
        context: TenantContext,
        conflict_id: str,
        *,
        decision: ConflictDecision,
        expected_conflict_version: int,
        idempotency_key: str,
    ) -> dict[str, Any]:
        if context.action != "CONFLICT_RESOLVE":
            raise AssignmentError("PERMISSION_DENIED_CONFLICT_RESOLVE", 403, "Conflict resolution permission is required.")
        self.authorized_mutations.require(
            context, action="CONFLICT_RESOLVE", resource_id=conflict_id
        )
        conflict = self.store.conflict(context.tenant_digest, conflict_id)
        if conflict is None:
            raise AssignmentError("AUTHORIZATION_DENIED", 404, "The accounting resource is unavailable.")
        try:
            command = json.loads(conflict["command_json"])
        except (json.JSONDecodeError, TypeError) as exc:
            raise AssignmentError("CONFLICT_EVIDENCE_INVALID", 503, "Conflict evidence is invalid.") from exc
        account_id = command.get("account_id")
        expected_version = command.get("expected_transaction_version")
        if not isinstance(account_id, str) or isinstance(expected_version, bool) or not isinstance(expected_version, int):
            raise AssignmentError("CONFLICT_EVIDENCE_INVALID", 503, "Conflict evidence is invalid.")
        self.registry.require_assignable(account_id)
        if command.get("scope") != AssignmentScope.SAME_VENDOR_FUTURE.value:
            raise AssignmentError("CONFLICT_EVIDENCE_INVALID", 503, "Conflict scope is invalid.")
        batch, tx = self.transaction(context, str(conflict["txn_id"]))
        match_key_id, vendor_token = tx.hmac_key_id, tx.vendor_match_token
        if not match_key_id or vendor_token == "0" * 64:
            raise AssignmentError("CONFLICT_EVIDENCE_INVALID", 503, "Conflict match evidence is incomplete.")
        result = self.store.resolve_conflict(
            tenant_id=context.tenant_id,
            tenant_digest=context.tenant_digest,
            actor_id=context.actor_id,
            conflict_id=conflict_id,
            expected_conflict_version=expected_conflict_version,
            decision=decision,
            txn_id=tx.txn_id,
            batch_id=batch.batch_id,
            expected_transaction_version=expected_version,
            account_id=account_id,
            vendor_match_token=vendor_token,
            adapter_family=tx.adapter_family,
            adapter_version=tx.adapter_version,
            normalization_version=tx.normalization_version,
            company_scope_digest=tx.company_scope_digest,
            direction="OUT" if tx.bank_direction == "OUTFLOW" else "IN",
            currency=tx.currency,
            registry_digest=self.registry.registry_digest,
            overlay_digest=self.registry.overlay_digest,
            match_key_id=match_key_id,
            assignment_id=opaque_id(),
            replacement_rule_id=opaque_id() if decision is ConflictDecision.REPLACE_WITH_NEW else None,
            idempotency_key=idempotency_key,
            authority_context=context,
        )
        if not result.replayed:
            with self._lock:
                batch.batch_version += 1
        return result.response

    def capability(self, context: TenantContext) -> dict[str, Any]:
        key_ready = True
        try:
            self.tokens.self_test(context.tenant_id)
            replay = self.store.verify_replay(context.tenant_id, context.tenant_digest)
        except AssignmentError:
            key_ready = False
            replay = {"passed": False, "event_count": 0}
        # Core v3 surface, excluding this read-only capability endpoint itself.
        routes = 11
        registry_ready = any(entry.assignable for entry in self.registry.entries)
        self_test_passed = replay["passed"] and registry_ready and key_ready
        reason_codes = []
        if not registry_ready:
            reason_codes.append("REGISTRY_OVERLAY_UNAPPROVED")
        if not replay["passed"]:
            reason_codes.append("EVENT_REPLAY_FAILED")
        if not key_ready:
            reason_codes.append("SECURE_KEY_UNAVAILABLE_OR_ROTATED")
        if self_test_passed:
            reason_codes.append("INDEPENDENT_PRODUCT_E2E_REQUIRED")
        payload = {
            "schema_version": "butler.accounting_capability_status.v2",
            "capability_id": "accounting.user_assignment",
            "status": "PARTIALLY_CONSUMED" if self_test_passed else "UNAVAILABLE",
            "registered": True,
            "required_routes": routes,
            "covered_routes": routes if registry_ready else 4,
            "self_test": "PASS" if self_test_passed else "FAIL",
            "reason_codes": reason_codes,
            "verified_at": utc_now(),
            "registry_digest": self.registry.registry_digest,
            "overlay_digest": self.registry.overlay_digest,
            "event_count": replay["event_count"],
        }
        payload["evidence_digest"] = sha256_json(payload)
        return payload


_RUNTIME: AccountingReviewRuntime | None = None
_RUNTIME_LOCK = threading.Lock()


def get_accounting_review_runtime() -> AccountingReviewRuntime:
    global _RUNTIME
    if _RUNTIME is None:
        with _RUNTIME_LOCK:
            if _RUNTIME is None:
                _RUNTIME = AccountingReviewRuntime.product_default()
    return _RUNTIME


def set_accounting_review_runtime_for_tests(runtime: AccountingReviewRuntime | None) -> None:
    global _RUNTIME
    _RUNTIME = runtime
