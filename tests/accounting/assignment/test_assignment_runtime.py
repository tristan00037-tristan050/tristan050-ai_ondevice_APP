from __future__ import annotations

import json
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import SimpleNamespace

import pytest

pd = pytest.importorskip("pandas")
jsonschema = pytest.importorskip("jsonschema")

from butler_pc_core.accounting.assignment.domain import (
    AssignCommand,
    AssignmentError,
    AssignmentScope,
    ConflictDecision,
)
from butler_pc_core.accounting.assignment.runtime import AccountingReviewRuntime
from butler_pc_core.accounting.assignment.registry import RegistryEntry, RegistrySnapshot
from butler_pc_core.accounting.assignment.security import MemoryKeyStore, TokenService


def _profile(name: str = "tenant-a"):
    digest = __import__("hashlib").sha256(name.encode()).hexdigest()
    return SimpleNamespace(status="ACTIVE", profile_id=name, profile_digest=digest)


def _frame(*, descriptor: str = "승인상호", account_column: dict[str, object] | None = None):
    row = {
        "거래일": "2026-07-16",
        "거래내용": descriptor,
        "금액": "-1200",
        "분류과목": "미분류",
    }
    row.update(account_column or {})
    return pd.DataFrame([row])


@pytest.fixture()
def runtime(tmp_path: Path) -> AccountingReviewRuntime:
    registry = RegistrySnapshot(
        registry_digest="1" * 64,
        overlay_digest="2" * 64,
        entries=(
            RegistryEntry("GROUP.TEST", None, "테스트 그룹", ("테스트 그룹",), "GROUP", False, "ACCOUNT_NODE_GROUP_NOT_ASSIGNABLE", 10),
            RegistryEntry("POSTING.A", "1001", "지급수수료", ("테스트 그룹", "지급수수료"), "POSTING", True, None, 20),
            RegistryEntry("POSTING.B", "1002", "소모품비", ("테스트 그룹", "소모품비"), "POSTING", True, None, 30),
        ),
    )
    return AccountingReviewRuntime(
        db_path=tmp_path / "assignment.sqlite3",
        key_store=MemoryKeyStore(key=b"a" * 32),
        registry=registry,
    )


def test_unapproved_bundled_overlay_publishes_no_assignable_accounts(tmp_path: Path):
    runtime = AccountingReviewRuntime(
        db_path=tmp_path / "unapproved.sqlite3",
        key_store=MemoryKeyStore(key=b"a" * 32),
    )
    assert runtime.registry.entries
    assert not any(entry.assignable for entry in runtime.registry.entries)
    capability = runtime.capability(runtime.context_from_profile(_profile()))
    assert capability["status"] == "UNAVAILABLE"
    assert "REGISTRY_OVERLAY_UNAPPROVED" in capability["reason_codes"]


def _first_assignable(runtime: AccountingReviewRuntime, *, exclude: str | None = None) -> str:
    return next(
        entry.account_id
        for entry in runtime.registry.entries
        if entry.assignable and entry.account_id != exclude
    )


def _command(runtime: AccountingReviewRuntime, account_id: str, scope: str = "THIS_ONLY", version: int = 1):
    return AssignCommand.from_dict(
        {
            "schema_version": "2.0",
            "account_id": account_id,
            "scope": scope,
            "registry_digest": runtime.registry.registry_digest,
            "expected_transaction_version": version,
        }
    )


def test_registry_assignable_is_server_calculated(runtime: AccountingReviewRuntime):
    group = next(entry for entry in runtime.registry.entries if entry.node_kind == "GROUP")
    posting = next(entry for entry in runtime.registry.entries if entry.assignable)

    with pytest.raises(AssignmentError, match="ACCOUNT_NOT_ASSIGNABLE"):
        runtime.registry.require_assignable(group.account_id)
    assert runtime.registry.require_assignable(posting.account_id) == posting


def test_account_column_ambiguity_requires_explicit_selection(runtime: AccountingReviewRuntime):
    result = runtime.ingest_dataframe(
        "batch_ambiguous_0001",
        _frame(account_column={"계정과목": "미확인", "account_id": "미확인"}),
        _profile(),
    )
    assert result["account_column_status"] == "SELECTION_REQUIRED"
    assert result["ambiguous_account_columns"] == ["계정과목", "account_id"]


def test_exact_account_column_removes_row_from_unaccounted(runtime: AccountingReviewRuntime):
    account_id = _first_assignable(runtime)
    runtime.ingest_dataframe(
        "batch_declared_00001",
        _frame(account_column={"계정과목": account_id}),
        _profile(),
        selected_account_column="계정과목",
    )
    context = runtime.context_from_profile(_profile())
    page = runtime.unaccounted_page(context, "batch_declared_00001", cursor=None, page_size=50)
    summary = runtime.review_summary(context, "batch_declared_00001")
    assert page["items"] == []
    assert summary["counts"]["source_declared_valid"] == 1


def test_fuzzy_account_cell_never_assigns(runtime: AccountingReviewRuntime):
    display_name = next(entry.display_name for entry in runtime.registry.entries if entry.assignable)
    runtime.ingest_dataframe(
        "batch_fuzzy_cell_01",
        _frame(account_column={"계정과목": display_name + " 유사"}),
        _profile(),
        selected_account_column="계정과목",
    )
    context = runtime.context_from_profile(_profile())
    page = runtime.unaccounted_page(context, "batch_fuzzy_cell_01", cursor=None, page_size=50)
    assert page["total_count"] == 1
    assert page["items"][0]["review_state"] == "REVIEW_REQUIRED"


def test_pagination_is_stable_tamper_evident_and_snapshot_bound(runtime: AccountingReviewRuntime):
    profile = _profile()
    context = runtime.context_from_profile(profile)
    frame = pd.DataFrame(
        [
            {"거래일": "2026-07-14", "거래내용": "거래 A", "금액": "-100", "분류과목": "미분류"},
            {"거래일": "2026-07-15", "거래내용": "거래 B", "금액": "-200", "분류과목": "미분류"},
            {"거래일": "2026-07-16", "거래내용": "거래 C", "금액": "-300", "분류과목": "미분류"},
        ]
    )
    runtime.ingest_dataframe("batch_pagination_001", frame, profile)
    first = runtime.unaccounted_page(context, "batch_pagination_001", cursor=None, page_size=1)
    second = runtime.unaccounted_page(context, "batch_pagination_001", cursor=first["next_cursor"], page_size=1)
    assert first["items"][0]["txn_id"] != second["items"][0]["txn_id"]
    cursor = first["next_cursor"]
    midpoint = len(cursor) // 2
    tampered = cursor[:midpoint] + ("A" if cursor[midpoint] != "A" else "B") + cursor[midpoint + 1 :]
    with pytest.raises(AssignmentError, match="INVALID_CURSOR"):
        runtime.unaccounted_page(
            context,
            "batch_pagination_001",
            cursor=tampered,
            page_size=1,
        )
    runtime.assign(
        context,
        first["items"][0]["txn_id"],
        _command(runtime, _first_assignable(runtime)),
        idempotency_key="idem-pagination-0001",
        if_match_version=1,
    )
    with pytest.raises(AssignmentError, match="BATCH_SNAPSHOT_CHANGED"):
        runtime.unaccounted_page(context, "batch_pagination_001", cursor=first["next_cursor"], page_size=1)


def test_stale_full_registry_digest_is_rejected(runtime: AccountingReviewRuntime):
    runtime.ingest_dataframe("batch_stale_registry", _frame(), _profile())
    context = runtime.context_from_profile(_profile())
    txn_id = runtime.unaccounted_page(context, "batch_stale_registry", cursor=None, page_size=50)["items"][0]["txn_id"]
    command = AssignCommand.from_dict(
        {
            "schema_version": "2.0",
            "account_id": _first_assignable(runtime),
            "scope": "THIS_ONLY",
            "registry_digest": "f" * 64,
            "expected_transaction_version": 1,
        }
    )
    with pytest.raises(AssignmentError, match="REGISTRY_STALE"):
        runtime.assign(context, txn_id, command, idempotency_key="idem-stale-registry1", if_match_version=1)
    assert runtime.store.current_assignment(context.tenant_digest, txn_id) is None


def test_assign_is_atomic_idempotent_and_raw_zero(runtime: AccountingReviewRuntime):
    runtime.ingest_dataframe("batch_assign_000001", _frame(), _profile())
    context = runtime.context_from_profile(_profile())
    tx = runtime.unaccounted_page(context, "batch_assign_000001", cursor=None, page_size=50)["items"][0]
    command = _command(runtime, _first_assignable(runtime))

    first = runtime.assign(context, tx["txn_id"], command, idempotency_key="idem-key-00000001", if_match_version=1)
    replay = runtime.assign(context, tx["txn_id"], command, idempotency_key="idem-key-00000001", if_match_version=1)

    assert first == replay
    assert first["state"] == "USER_ASSIGNED"
    assert first["rule_effect"] == "NONE"
    assert runtime.store.verify_replay(context.tenant_id, context.tenant_digest)["event_count"] == 1
    db_bytes = runtime.store.path.read_bytes()
    assert "승인상호".encode() not in db_bytes
    schema = json.loads(
        (
            Path(__file__).resolve().parents[3]
            / "butler_pc_core/accounting/assignment/contracts/assignment_event.schema.json"
        ).read_text(encoding="utf-8")
    )
    with sqlite3.connect(runtime.store.path) as conn:
        payloads = [json.loads(row[0]) for row in conn.execute("SELECT payload_json FROM assignment_events")]
    for payload in payloads:
        jsonschema.Draft202012Validator(schema, format_checker=jsonschema.FormatChecker()).validate(payload)


def test_same_idempotency_key_different_body_is_blocked(runtime: AccountingReviewRuntime):
    runtime.ingest_dataframe("batch_idem_00000001", _frame(), _profile())
    context = runtime.context_from_profile(_profile())
    txn_id = runtime.unaccounted_page(context, "batch_idem_00000001", cursor=None, page_size=50)["items"][0]["txn_id"]
    first_account = _first_assignable(runtime)
    runtime.assign(
        context,
        txn_id,
        _command(runtime, first_account),
        idempotency_key="idem-key-00000002",
        if_match_version=1,
    )
    with pytest.raises(AssignmentError, match="IDEMPOTENCY_KEY_REUSED_WITH_DIFFERENT_BODY"):
        runtime.assign(
            context,
            txn_id,
            _command(runtime, _first_assignable(runtime, exclude=first_account)),
            idempotency_key="idem-key-00000002",
            if_match_version=1,
        )


def test_two_windows_same_version_allow_exactly_one_assignment(runtime: AccountingReviewRuntime):
    runtime.ingest_dataframe("batch_concurrent_001", _frame(), _profile())
    context = runtime.context_from_profile(_profile())
    txn_id = runtime.unaccounted_page(context, "batch_concurrent_001", cursor=None, page_size=50)["items"][0]["txn_id"]
    command = _command(runtime, _first_assignable(runtime))

    def assign(key: str):
        try:
            return runtime.assign(context, txn_id, command, idempotency_key=key, if_match_version=1)["state"]
        except AssignmentError as exc:
            return exc.code

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(assign, ("idem-concurrent-0001", "idem-concurrent-0002")))
    assert sorted(outcomes) == ["TRANSACTION_STALE", "USER_ASSIGNED"]
    assert runtime.store.verify_replay(context.tenant_id, context.tenant_digest)["event_count"] == 1


def test_stale_write_and_cross_tenant_access_are_blocked(runtime: AccountingReviewRuntime):
    runtime.ingest_dataframe("batch_auth_00000001", _frame(), _profile())
    context = runtime.context_from_profile(_profile())
    txn_id = runtime.unaccounted_page(context, "batch_auth_00000001", cursor=None, page_size=50)["items"][0]["txn_id"]
    with pytest.raises(AssignmentError, match="TRANSACTION_STALE"):
        runtime.assign(
            context,
            txn_id,
            _command(runtime, _first_assignable(runtime), version=2),
            idempotency_key="idem-key-00000003",
            if_match_version=1,
        )
    with pytest.raises(AssignmentError, match="AUTHORIZATION_DENIED"):
        runtime.transaction(runtime.context_from_profile(_profile("tenant-b")), txn_id)


def test_expired_batch_removes_authorized_raw_projection(runtime: AccountingReviewRuntime):
    runtime.ingest_dataframe("batch_expired_00001", _frame(descriptor="만료 원문"), _profile())
    context = runtime.context_from_profile(_profile())
    assert runtime.unaccounted_page(context, "batch_expired_00001", cursor=None, page_size=50)["total_count"] == 1
    runtime.remove_batch("batch_expired_00001")
    with pytest.raises(AssignmentError, match="AUTHORIZATION_DENIED"):
        runtime.unaccounted_page(context, "batch_expired_00001", cursor=None, page_size=50)


def test_future_rule_is_suggestion_and_deactivation_stops_match(runtime: AccountingReviewRuntime):
    profile = _profile()
    context = runtime.context_from_profile(profile)
    account_id = _first_assignable(runtime)
    runtime.ingest_dataframe("batch_rule_one_0001", _frame(descriptor="동일상호"), profile)
    txn_id = runtime.unaccounted_page(context, "batch_rule_one_0001", cursor=None, page_size=50)["items"][0]["txn_id"]
    assigned = runtime.assign(
        context,
        txn_id,
        _command(runtime, account_id, "SAME_VENDOR_FUTURE"),
        idempotency_key="idem-key-00000004",
        if_match_version=1,
    )
    assert assigned["state"] == "USER_ASSIGNED"
    assert assigned["rule_effect"] == "SUGGESTION_CREATED"

    runtime.ingest_dataframe("batch_rule_two_0002", _frame(descriptor="동일상호"), profile)
    suggested = runtime.unaccounted_page(context, "batch_rule_two_0002", cursor=None, page_size=50)["items"][0]
    assert suggested["review_state"] == "USER_RULE_SUGGESTED"
    assert suggested["suggestion"]["account_id"] == account_id

    off = runtime.deactivate_rule(
        context,
        assigned["rule_id"],
        idempotency_key="idem-key-00000005",
        if_match_version=1,
    )
    replay = runtime.deactivate_rule(
        context,
        assigned["rule_id"],
        idempotency_key="idem-key-00000005",
        if_match_version=1,
    )
    assert off == replay
    runtime.ingest_dataframe("batch_rule_three_03", _frame(descriptor="동일상호"), profile)
    after = runtime.unaccounted_page(context, "batch_rule_three_03", cursor=None, page_size=50)["items"][0]
    assert after["review_state"] == "REVIEW_REQUIRED"


def test_conflicting_rule_blocks_assignment_and_rule_replacement(runtime: AccountingReviewRuntime):
    profile = _profile()
    context = runtime.context_from_profile(profile)
    account_a = _first_assignable(runtime)
    account_b = _first_assignable(runtime, exclude=account_a)
    runtime.ingest_dataframe("batch_conflict_a_01", _frame(descriptor="충돌상호"), profile)
    txn_a = runtime.unaccounted_page(context, "batch_conflict_a_01", cursor=None, page_size=50)["items"][0]["txn_id"]
    runtime.assign(
        context,
        txn_a,
        _command(runtime, account_a, "SAME_VENDOR_FUTURE"),
        idempotency_key="idem-key-00000006",
        if_match_version=1,
    )
    runtime.ingest_dataframe("batch_conflict_b_02", _frame(descriptor="충돌상호"), profile)
    txn_b = runtime.unaccounted_page(context, "batch_conflict_b_02", cursor=None, page_size=50)["items"][0]["txn_id"]
    with pytest.raises(AssignmentError, match="LEARNED_RULE_CONFLICT") as caught:
        runtime.assign(
            context,
            txn_b,
            _command(runtime, account_b, "SAME_VENDOR_FUTURE"),
            idempotency_key="idem-key-00000007",
            if_match_version=1,
        )
    assert runtime.store.current_assignment(context.tenant_digest, txn_b) is None
    assert len(runtime.store.list_rules(context.tenant_digest, "ACTIVE_SUGGESTION")) == 1

    conflict_id = caught.value.actions[0].split(":", 1)[1]
    replaced = runtime.resolve_conflict(
        context,
        conflict_id,
        decision=ConflictDecision.REPLACE_WITH_NEW,
        expected_conflict_version=1,
        idempotency_key="idem-key-00000009",
    )
    replay = runtime.resolve_conflict(
        context,
        conflict_id,
        decision=ConflictDecision.REPLACE_WITH_NEW,
        expected_conflict_version=1,
        idempotency_key="idem-key-00000009",
    )
    assert replaced == replay
    assert replaced["rule_effect"] == "SUGGESTION_REPLACED"
    active = runtime.store.list_rules(context.tenant_digest, "ACTIVE_SUGGESTION")
    inactive = runtime.store.list_rules(context.tenant_digest, "INACTIVE_USER")
    assert [row["account_id"] for row in active] == [account_b]
    assert [row["account_id"] for row in inactive] == [account_a]
    assert runtime.store.current_assignment(context.tenant_digest, txn_b)["account_id"] == account_b


def test_conflict_keep_existing_assigns_current_transaction_only(runtime: AccountingReviewRuntime):
    profile = _profile()
    context = runtime.context_from_profile(profile)
    account_a = _first_assignable(runtime)
    account_b = _first_assignable(runtime, exclude=account_a)
    runtime.ingest_dataframe("batch_keep_rule_a01", _frame(descriptor="유지상호"), profile)
    txn_a = runtime.unaccounted_page(context, "batch_keep_rule_a01", cursor=None, page_size=50)["items"][0]["txn_id"]
    runtime.assign(
        context,
        txn_a,
        _command(runtime, account_a, "SAME_VENDOR_FUTURE"),
        idempotency_key="idem-key-00000010",
        if_match_version=1,
    )
    runtime.ingest_dataframe("batch_keep_rule_b02", _frame(descriptor="유지상호"), profile)
    txn_b = runtime.unaccounted_page(context, "batch_keep_rule_b02", cursor=None, page_size=50)["items"][0]["txn_id"]
    with pytest.raises(AssignmentError, match="LEARNED_RULE_CONFLICT") as caught:
        runtime.assign(
            context,
            txn_b,
            _command(runtime, account_b, "SAME_VENDOR_FUTURE"),
            idempotency_key="idem-key-00000011",
            if_match_version=1,
        )
    conflict_id = caught.value.actions[0].split(":", 1)[1]
    kept = runtime.resolve_conflict(
        context,
        conflict_id,
        decision=ConflictDecision.KEEP_EXISTING,
        expected_conflict_version=1,
        idempotency_key="idem-key-00000012",
    )
    assert kept["rule_effect"] == "EXISTING_SUGGESTION_KEPT"
    assert runtime.store.current_assignment(context.tenant_digest, txn_b)["account_id"] == account_b
    assert [row["account_id"] for row in runtime.store.list_rules(context.tenant_digest, "ACTIVE_SUGGESTION")] == [account_a]


def test_event_table_rejects_update_and_key_rotation_fails_closed(runtime: AccountingReviewRuntime):
    profile = _profile()
    context = runtime.context_from_profile(profile)
    runtime.ingest_dataframe("batch_chain_0000001", _frame(), profile)
    txn_id = runtime.unaccounted_page(context, "batch_chain_0000001", cursor=None, page_size=50)["items"][0]["txn_id"]
    runtime.assign(
        context,
        txn_id,
        _command(runtime, _first_assignable(runtime)),
        idempotency_key="idem-key-00000008",
        if_match_version=1,
    )
    with sqlite3.connect(runtime.store.path) as conn, pytest.raises(sqlite3.IntegrityError, match="APPEND_ONLY_EVENT"):
        conn.execute("UPDATE assignment_events SET event_type='RULE_CREATED'")
    with sqlite3.connect(runtime.store.path) as conn, pytest.raises(sqlite3.IntegrityError, match="APPEND_ONLY_EVENT"):
        conn.execute("DELETE FROM assignment_events")

    rotated = AccountingReviewRuntime(
        db_path=runtime.store.path,
        key_store=MemoryKeyStore(key=b"b" * 32, key_id="rotated-test-key"),
        registry=runtime.registry,
    )
    with pytest.raises(AssignmentError, match="EVENT_CHECKPOINT_INVALID"):
        rotated.store.verify_replay(context.tenant_id, context.tenant_digest)
    rotated.ingest_dataframe("batch_rotated_key_01", _frame(descriptor="회전상호"), profile)
    rotated_txn = rotated.unaccounted_page(context, "batch_rotated_key_01", cursor=None, page_size=50)["items"][0]["txn_id"]
    with pytest.raises(AssignmentError, match="EVENT_CHECKPOINT_INVALID"):
        rotated.assign(
            context,
            rotated_txn,
            _command(rotated, _first_assignable(rotated)),
            idempotency_key="idem-key-rotated-001",
            if_match_version=1,
        )
    assert rotated.store.current_assignment(context.tenant_digest, rotated_txn) is None


def test_assignment_and_rule_roll_back_on_second_event_failure(runtime: AccountingReviewRuntime, monkeypatch):
    profile = _profile()
    context = runtime.context_from_profile(profile)
    runtime.ingest_dataframe("batch_partial_commit1", _frame(), profile)
    txn_id = runtime.unaccounted_page(context, "batch_partial_commit1", cursor=None, page_size=50)["items"][0]["txn_id"]
    original = runtime.store._append_event
    calls = 0

    def fail_second(*args, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise sqlite3.OperationalError("injected write failure")
        return original(*args, **kwargs)

    monkeypatch.setattr(runtime.store, "_append_event", fail_second)
    with pytest.raises(AssignmentError, match="EVENT_CHECKPOINT_INVALID"):
        runtime.assign(
            context,
            txn_id,
            _command(runtime, _first_assignable(runtime), "SAME_VENDOR_FUTURE"),
            idempotency_key="idem-partial-commit1",
            if_match_version=1,
        )
    assert runtime.store.current_assignment(context.tenant_digest, txn_id) is None
    assert runtime.store.list_rules(context.tenant_digest) == []
    assert runtime.store.verify_replay(context.tenant_id, context.tenant_digest)["event_count"] == 0


def test_tenant_tokens_are_unlinkable_and_keystore_failure_degrades_capability(tmp_path: Path):
    service = TokenService(MemoryKeyStore(key=b"t" * 32))
    _, token_a = service.vendor_token("tenant-a", "bank_dataframe_v1", "동일 거래처")
    _, token_b = service.vendor_token("tenant-b", "bank_dataframe_v1", "동일 거래처")
    assert token_a != token_b

    class FailingKeyStore:
        def root_key(self):
            raise AssignmentError("SECURE_KEY_UNAVAILABLE", 503, "unavailable")

    runtime = AccountingReviewRuntime(
        db_path=tmp_path / "keystore-failure.sqlite3",
        key_store=FailingKeyStore(),
        registry=RegistrySnapshot(
            registry_digest="5" * 64,
            overlay_digest="6" * 64,
            entries=(RegistryEntry("POSTING.X", "3001", "통신비", ("통신비",), "POSTING", True, None, 1),),
        ),
    )
    capability = runtime.capability(runtime.context_from_profile(_profile()))
    assert capability["status"] == "UNAVAILABLE"
    assert "SECURE_KEY_UNAVAILABLE_OR_ROTATED" in capability["reason_codes"]


def test_persisted_rows_do_not_contain_forbidden_raw_keys(runtime: AccountingReviewRuntime):
    columns = {row[1] for row in sqlite3.connect(runtime.store.path).execute("PRAGMA table_info(learned_rules)")}
    forbidden = {"descriptor", "descriptor_display", "memo", "account_number", "raw_text", "canonical_descriptor"}
    assert not (columns & forbidden)
