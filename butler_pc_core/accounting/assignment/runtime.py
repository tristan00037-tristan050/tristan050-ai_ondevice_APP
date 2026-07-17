"""Product runtime connecting classified bank rows to assignment services."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import math
import re
import threading
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
                "SECURE_KEY_PROVIDER_NOT_PRODUCTION",
                503,
                "Production accounting requires the platform Keychain key store.",
            )
        return cls(db_path=db_path, key_store=key_store, registry=registry)

    @staticmethod
    def context_from_profile(profile: Any) -> TenantContext:
        if profile is None or getattr(profile, "status", None) != "ACTIVE":
            raise AssignmentError(
                "BLOCK_SECURE_TRANSACTION_PROJECTION_UNAVAILABLE",
                503,
                "An active company profile is required for accounting review.",
            )
        tenant_id = str(profile.profile_id)
        tenant_digest = _digest(tenant_id + ":" + str(profile.profile_digest))
        actor_id = "actor_" + _digest("local-user:" + tenant_id)[:32]
        return TenantContext(tenant_id, tenant_digest, actor_id)

    def ingest_dataframe(
        self,
        batch_id: str,
        frame: Any,
        company_profile: Any,
        *,
        selected_account_column: str | None = None,
    ) -> dict[str, Any]:
        context = self.context_from_profile(company_profile)
        if not re.fullmatch(r"[A-Za-z0-9_-]{16,128}", batch_id):
            raise AssignmentError("BATCH_ID_INVALID", 422, "Batch identifier is invalid.")
        resolution = resolve_account_column(
            list(frame.columns), selected_column=selected_account_column
        )
        account_by_name = {entry.display_name: entry for entry in self.registry.entries if entry.assignable}
        transactions: dict[str, CanonicalReviewTransaction] = {}
        quarantined: list[dict[str, Any]] = []
        key_id: str | None = None
        for sequence, (_, row) in enumerate(frame.iterrows()):
            amount = _to_amount(row)
            if amount is None or amount == 0:
                continue
            descriptor, descriptor_display, display_policy = _descriptor(row)
            booked_date = _parse_booked_date(
                next((row.get(c) for c in _DATE_COLUMNS if c in row.index), None)
            )
            if booked_date is None:
                # ★ RI-P0-010: 잘못된/누락 날짜는 1970 대체 없이 격리하고 사용자 수정을 요구한다.
                quarantined.append(
                    {
                        "source_sequence": sequence,
                        "reason_code": "INVALID_TRANSACTION_DATE",
                        "descriptor_display": descriptor_display,
                        "display_policy": display_policy,
                    }
                )
                continue
            adapter_family = "bank_dataframe_v1"
            key_id, vendor_token = self.tokens.vendor_token(context.tenant_id, adapter_family, descriptor)
            source_payload = {
                "batch": batch_id,
                "sequence": sequence,
                "booked": str(next((row.get(c) for c in _DATE_COLUMNS if c in row.index), "")),
                "amount": amount,
                "descriptor_digest": _digest(descriptor),
            }
            source_digest = sha256_json(source_payload)
            txn_id = "txn_" + _digest(context.tenant_digest + source_digest)[:40]
            declared = None
            if resolution.selected_column is not None:
                declared = resolve_account_cell(row.get(resolution.selected_column), self.registry)
            legacy_name = _cell_text(row.get("분류과목"))
            active_rule = self.store.active_rule(
                context.tenant_digest, vendor_token, adapter_family, NORMALIZATION_VERSION
            )
            suggestion_account: str | None = None
            suggestion_rule: str | None = None
            safe_reason: str | None = None
            if declared is not None:
                state = ReviewState.SOURCE_DECLARED_VALID
                suggestion_account = declared.account_id
                safe_reason = "업로드 파일의 계정 열을 정확히 확인했습니다."
            elif active_rule is not None:
                state = ReviewState.USER_RULE_SUGGESTED
                suggestion_account = str(active_rule["account_id"])
                suggestion_rule = str(active_rule["rule_id"])
                safe_reason = "과거 사용자 선택과 정확히 일치해 제안합니다. 확인이 필요합니다."
            elif legacy_name in account_by_name:
                state = ReviewState.AUTO_PROPOSE
                suggestion_account = account_by_name[legacy_name].account_id
                safe_reason = "기존 정확 규칙이 제안했습니다. 확인이 필요합니다."
            else:
                state = ReviewState.REVIEW_REQUIRED
            transactions[txn_id] = CanonicalReviewTransaction(
                tenant_digest=context.tenant_digest,
                batch_id=batch_id,
                txn_id=txn_id,
                source_sequence=sequence,
                booked_date=booked_date,
                amount_minor=amount,
                currency="KRW",
                bank_direction="OUTFLOW" if amount < 0 else "INFLOW",
                transaction_version=1,
                canonical_descriptor=descriptor,
                descriptor_display=descriptor_display,
                display_policy=display_policy,
                vendor_match_token=vendor_token,
                adapter_family=adapter_family,
                normalization_version=NORMALIZATION_VERSION,
                source_record_digest=source_digest,
                review_state=state,
                suggestion_account_id=suggestion_account,
                suggestion_rule_id=suggestion_rule,
                safe_reason=safe_reason,
            )
        batch = ReviewBatch(
            context=context,
            batch_id=batch_id,
            batch_version=1,
            transactions=transactions,
            ambiguous_account_columns=resolution.ambiguous_columns,
            quarantined=tuple(quarantined),
        )
        with self._lock:
            self._batches[batch_id] = batch
        return {
            "batch_id": batch_id,
            "review_count": sum(
                tx.review_state not in {ReviewState.SOURCE_DECLARED_VALID, ReviewState.NON_EXPENSE_BANK_EVENT}
                for tx in transactions.values()
            ),
            "quarantine_count": len(quarantined),
            "account_column_status": (
                "SELECTION_REQUIRED" if resolution.ambiguous_columns else "RESOLVED"
            ),
            "ambiguous_account_columns": list(resolution.ambiguous_columns),
            "match_key_id": key_id,
            "registry_digest": self.registry.registry_digest,
            "overlay_digest": self.registry.overlay_digest,
        }

    def _batch(self, context: TenantContext, batch_id: str) -> ReviewBatch:
        with self._lock:
            batch = self._batches.get(batch_id)
        if batch is None or batch.context.tenant_digest != context.tenant_digest:
            # Deliberately identical for absent and cross-tenant objects.
            raise AssignmentError("AUTHORIZATION_DENIED", 404, "The accounting resource is unavailable.")
        return batch

    def remove_batch(self, batch_id: str) -> None:
        with self._lock:
            self._batches.pop(batch_id, None)

    def transaction(self, context: TenantContext, txn_id: str) -> tuple[ReviewBatch, CanonicalReviewTransaction]:
        with self._lock:
            candidates = list(self._batches.values())
        for batch in candidates:
            if batch.context.tenant_digest == context.tenant_digest and txn_id in batch.transactions:
                return batch, batch.transactions[txn_id]
        raise AssignmentError("AUTHORIZATION_DENIED", 404, "The accounting resource is unavailable.")

    def review_summary(self, context: TenantContext, batch_id: str) -> dict[str, Any]:
        batch = self._batch(context, batch_id)
        counts = {
            "source_declared_valid": 0,
            "auto_propose": 0,
            "user_rule_suggested": 0,
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
            "schema_version": "2.0",
            "batch_id": batch_id,
            "batch_version": batch.batch_version,
            "registry_digest": self.registry.registry_digest,
            "overlay_digest": self.registry.overlay_digest,
            "counts": counts,
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
            if tx.review_state not in {ReviewState.SOURCE_DECLARED_VALID, ReviewState.NON_EXPENSE_BANK_EVENT}
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
            "schema_version": "2.0",
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
        command.registry_digest and self.registry.require_digest(command.registry_digest)
        self.registry.require_assignable(command.account_id)
        if command.expected_transaction_version != if_match_version:
            raise AssignmentError(
                "TRANSACTION_STALE",
                412,
                "The transaction changed before assignment.",
                actions=("REFRESH_TRANSACTION",),
                current_version=command.expected_transaction_version,
            )
        match_key_id, recalculated_token = self.tokens.vendor_token(
            context.tenant_id, tx.adapter_family, tx.canonical_descriptor
        )
        if not hmac.compare_digest(recalculated_token, tx.vendor_match_token):
            raise AssignmentError("CANONICAL_TRANSACTION_INVALID", 503, "Server transaction evidence changed.")
        assignment_id = opaque_id()
        active_rule = self.store.active_rule(
            context.tenant_digest,
            recalculated_token,
            tx.adapter_family,
            tx.normalization_version,
        )
        should_create_rule = (
            command.scope is AssignmentScope.SAME_VENDOR_FUTURE
            and (active_rule is None or active_rule["account_id"] != command.account_id)
        )
        rule_id = opaque_id() if should_create_rule else None
        result = self.store.create_assignment(
            tenant_id=context.tenant_id,
            tenant_digest=context.tenant_digest,
            actor_id=context.actor_id,
            txn_id=txn_id,
            batch_id=batch.batch_id,
            expected_version=command.expected_transaction_version,
            account_id=command.account_id,
            scope=command.scope.value,
            vendor_match_token=recalculated_token,
            adapter_family=tx.adapter_family,
            normalization_version=tx.normalization_version,
            registry_digest=self.registry.registry_digest,
            overlay_digest=self.registry.overlay_digest,
            match_key_id=match_key_id,
            assignment_id=assignment_id,
            rule_id=rule_id,
            idempotency_key=idempotency_key,
            body={
                "schema_version": "2.0",
                "account_id": command.account_id,
                "scope": command.scope.value,
                "registry_digest": command.registry_digest,
                "expected_transaction_version": command.expected_transaction_version,
            },
        )
        if not result.replayed:
            with self._lock:
                batch.batch_version += 1
        return result.response

    def learned_rules(self, context: TenantContext, state: str | None = None) -> dict[str, Any]:
        allowed_states = {"ACTIVE_SUGGESTION", "INACTIVE_USER", "INACTIVE_REGISTRY", "DEGRADED_KEY_ROTATION"}
        if state is not None and state not in allowed_states:
            raise AssignmentError("INVALID_REQUEST_SCHEMA", 422, "Rule state is invalid.")
        rows = self.store.list_rules(context.tenant_digest, state)
        return {
            "schema_version": "2.0",
            "items": [
                {
                    "schema_version": "2.0",
                    "rule_id": row["rule_id"],
                    "account_id": row["account_id"],
                    "source_assignment_id": row["source_assignment_id"],
                    "state": row["state"],
                    "registry_digest": row["registry_digest"],
                    "overlay_digest": row["overlay_digest"],
                    "match_key_id": row["match_key_id"],
                    "normalization_version": row["normalization_version"],
                    "created_at": row["created_at"],
                    "deactivated_at": row["deactivated_at"],
                    "resource_version": row["resource_version"],
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
        return self.store.deactivate_rule(
            tenant_id=context.tenant_id,
            tenant_digest=context.tenant_digest,
            actor_id=context.actor_id,
            rule_id=rule_id,
            expected_version=if_match_version,
            registry_digest=self.registry.registry_digest,
            overlay_digest=self.registry.overlay_digest,
            idempotency_key=idempotency_key,
        )

    def resolve_conflict(
        self,
        context: TenantContext,
        conflict_id: str,
        *,
        decision: ConflictDecision,
        expected_conflict_version: int,
        idempotency_key: str,
    ) -> dict[str, Any]:
        conflict = self.store.conflict(context.tenant_digest, conflict_id)
        if conflict is None:
            raise AssignmentError("AUTHORIZATION_DENIED", 404, "The accounting resource is unavailable.")
        try:
            command = AssignCommand.from_dict(json.loads(conflict["command_json"]))
        except (json.JSONDecodeError, TypeError, AssignmentError) as exc:
            raise AssignmentError("CONFLICT_EVIDENCE_INVALID", 503, "Conflict evidence is invalid.") from exc
        self.registry.require_digest(command.registry_digest)
        self.registry.require_assignable(command.account_id)
        if command.scope is not AssignmentScope.SAME_VENDOR_FUTURE:
            raise AssignmentError("CONFLICT_EVIDENCE_INVALID", 503, "Conflict scope is invalid.")
        batch, tx = self.transaction(context, str(conflict["txn_id"]))
        match_key_id, vendor_token = self.tokens.vendor_token(
            context.tenant_id, tx.adapter_family, tx.canonical_descriptor
        )
        if not hmac.compare_digest(vendor_token, tx.vendor_match_token):
            raise AssignmentError("CANONICAL_TRANSACTION_INVALID", 503, "Server transaction evidence changed.")
        result = self.store.resolve_conflict(
            tenant_id=context.tenant_id,
            tenant_digest=context.tenant_digest,
            actor_id=context.actor_id,
            conflict_id=conflict_id,
            expected_conflict_version=expected_conflict_version,
            decision=decision,
            txn_id=tx.txn_id,
            batch_id=batch.batch_id,
            expected_transaction_version=command.expected_transaction_version,
            account_id=command.account_id,
            vendor_match_token=vendor_token,
            adapter_family=tx.adapter_family,
            normalization_version=tx.normalization_version,
            registry_digest=self.registry.registry_digest,
            overlay_digest=self.registry.overlay_digest,
            match_key_id=match_key_id,
            assignment_id=opaque_id(),
            replacement_rule_id=opaque_id() if decision is ConflictDecision.REPLACE_WITH_NEW else None,
            idempotency_key=idempotency_key,
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
        routes = 8
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
