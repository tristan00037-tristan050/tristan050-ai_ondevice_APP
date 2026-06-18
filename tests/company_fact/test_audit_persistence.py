from __future__ import annotations

import inspect
import json
from pathlib import Path

import pytest

from butler_pc_core.company_fact.audit import CompanyFactAuditLoadError, CompanyFactAuditStore
from butler_pc_core.company_fact.storage import CompanyFactStore
from butler_pc_core.company_policy.contracts import AdminContext, sha256_text


ANSWER_TEXT = "Company private approval answer stored in encrypted vault only."
QUESTION_TEXT = "What is the company private accounting rule?"
SOURCE_TEXT = "Private company source text kept out of audit logs."


def _admin() -> AdminContext:
    return AdminContext(
        admin_id_digest=sha256_text("company-fact-audit-admin"),
        role="admin",
        admin_session_digest=sha256_text("company-fact-audit-session"),
        auth_method="tauri_secure_invoke",
    )


def _candidate(store: CompanyFactStore):
    return store.save_candidate(
        category="company_rules",
        question_patterns=[QUESTION_TEXT, "private accounting policy"],
        keywords_required=["accounting"],
        keywords_any=["policy"],
        answer_runtime_text=ANSWER_TEXT,
        source=SOURCE_TEXT,
        source_doc="private-source-doc",
        confidence=0.5,
    )


def _read_jsonl(path: Path) -> list[dict[str, object]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def test_append_persists_log_line_and_head_checkpoint(tmp_path):
    store = CompanyFactAuditStore(root=tmp_path)
    record = store.append(
        action="company_fact.candidate",
        fact_digest=sha256_text("candidate-fact"),
        reason_code="CANDIDATE_SUBMITTED",
    )

    log_rows = _read_jsonl(tmp_path / "audit_log.jsonl")
    head = json.loads((tmp_path / "audit_head.json").read_text(encoding="utf-8"))

    assert log_rows == [record]
    assert head["schema_version"] == "company_fact.audit_head.v1"
    assert head["record_count"] == 1
    assert head["last_audit_id"] == record["audit_id"]
    assert head["raw_text_logged"] is False
    assert head["external_send_zero"] is True


def test_records_restore_from_same_root_and_chain_previous_digest(tmp_path):
    store = CompanyFactAuditStore(root=tmp_path)
    first = store.append(
        action="company_fact.candidate",
        fact_digest=sha256_text("candidate-fact"),
        reason_code="CANDIDATE_SUBMITTED",
    )
    second = store.append(
        action="company_fact.active",
        fact_digest=sha256_text("active-fact"),
        actor_digest=sha256_text("approver"),
        reason_code="CANDIDATE_APPROVED",
    )

    restored = CompanyFactAuditStore(root=tmp_path)

    assert len(restored.records) == 2
    assert restored.records[0]["audit_id"] == first["audit_id"]
    assert restored.records[1]["audit_id"] == second["audit_id"]
    assert restored.records[1]["prev_audit_digest"] == first["audit_id"]


def test_append_refreshes_persisted_state_before_sequence_assignment(tmp_path):
    first_store = CompanyFactAuditStore(root=tmp_path)
    second_store = CompanyFactAuditStore(root=tmp_path)

    first = first_store.append(
        action="company_fact.candidate",
        fact_digest=sha256_text("candidate-fact"),
        reason_code="CANDIDATE_SUBMITTED",
    )
    second = second_store.append(
        action="company_fact.active",
        fact_digest=sha256_text("active-fact"),
        reason_code="CANDIDATE_APPROVED",
    )
    restored = CompanyFactAuditStore(root=tmp_path)

    assert [record["sequence"] for record in restored.records] == [1, 2]
    assert restored.records[1]["audit_id"] == second["audit_id"]
    assert restored.records[1]["prev_audit_digest"] == first["audit_id"]


def test_tampered_middle_line_fails_closed(tmp_path):
    store = CompanyFactAuditStore(root=tmp_path)
    store.append(
        action="company_fact.candidate",
        fact_digest=sha256_text("candidate-fact"),
        reason_code="CANDIDATE_SUBMITTED",
    )
    store.append(
        action="company_fact.active",
        fact_digest=sha256_text("active-fact"),
        reason_code="CANDIDATE_APPROVED",
    )
    store.append(
        action="company_fact.deprecated",
        fact_digest=sha256_text("deprecated-fact"),
        reason_code="ACTIVE_DEPRECATED",
    )
    rows = _read_jsonl(tmp_path / "audit_log.jsonl")
    rows[1]["reason_code"] = "TAMPERED"
    (tmp_path / "audit_log.jsonl").write_text(
        "\n".join(json.dumps(row, ensure_ascii=False, sort_keys=True) for row in rows) + "\n",
        encoding="utf-8",
    )

    with pytest.raises(CompanyFactAuditLoadError):
        CompanyFactAuditStore(root=tmp_path)


def test_deleted_middle_line_fails_closed(tmp_path):
    store = CompanyFactAuditStore(root=tmp_path)
    store.append(
        action="company_fact.candidate",
        fact_digest=sha256_text("candidate-fact"),
        reason_code="CANDIDATE_SUBMITTED",
    )
    store.append(
        action="company_fact.active",
        fact_digest=sha256_text("active-fact"),
        reason_code="CANDIDATE_APPROVED",
    )
    store.append(
        action="company_fact.deprecated",
        fact_digest=sha256_text("deprecated-fact"),
        reason_code="ACTIVE_DEPRECATED",
    )
    rows = _read_jsonl(tmp_path / "audit_log.jsonl")
    del rows[1]
    (tmp_path / "audit_log.jsonl").write_text(
        "\n".join(json.dumps(row, ensure_ascii=False, sort_keys=True) for row in rows) + "\n",
        encoding="utf-8",
    )

    with pytest.raises(CompanyFactAuditLoadError):
        CompanyFactAuditStore(root=tmp_path)


def test_tail_truncation_with_head_mismatch_fails_closed(tmp_path):
    store = CompanyFactAuditStore(root=tmp_path)
    store.append(
        action="company_fact.candidate",
        fact_digest=sha256_text("candidate-fact"),
        reason_code="CANDIDATE_SUBMITTED",
    )
    store.append(
        action="company_fact.active",
        fact_digest=sha256_text("active-fact"),
        reason_code="CANDIDATE_APPROVED",
    )
    rows = _read_jsonl(tmp_path / "audit_log.jsonl")
    (tmp_path / "audit_log.jsonl").write_text(
        json.dumps(rows[0], ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    with pytest.raises(CompanyFactAuditLoadError):
        CompanyFactAuditStore(root=tmp_path)


def test_audit_log_is_digest_only_and_avoids_runtime_text(tmp_path):
    fact_digest = sha256_text("private fact")
    store = CompanyFactAuditStore(root=tmp_path)
    store.append(
        action="company_fact.candidate",
        fact_digest=fact_digest,
        actor_digest=sha256_text("actor"),
        reason_code="CANDIDATE_SUBMITTED",
    )
    text = (tmp_path / "audit_log.jsonl").read_text(encoding="utf-8")

    assert "sha256:" in text
    assert ANSWER_TEXT not in text
    assert QUESTION_TEXT not in text
    assert SOURCE_TEXT not in text
    assert ("source_text" + "_runtime") not in text
    assert ("raw" + "_document") not in text


def test_append_signature_is_compatible():
    signature = inspect.signature(CompanyFactAuditStore.append)

    assert list(signature.parameters) == [
        "self",
        "action",
        "fact_digest",
        "actor_digest",
        "reason_code",
    ]


def test_company_fact_store_persists_candidate_approve_and_deprecate_audits(tmp_path):
    store = CompanyFactStore(root=tmp_path / "facts")

    entry, candidate_audit = _candidate(store)
    active, approve_audit = store.approve_candidate(entry.fact_id, _admin())
    deprecated, deprecate_audit = store.deprecate_fact(active.fact_id, _admin())
    restored = CompanyFactAuditStore(root=tmp_path / "facts")
    log_text = (tmp_path / "facts" / "audit_log.jsonl").read_text(encoding="utf-8")

    assert [record["audit_id"] for record in restored.records] == [
        candidate_audit["audit_id"],
        approve_audit["audit_id"],
        deprecate_audit["audit_id"],
    ]
    assert restored.records[1]["prev_audit_digest"] == restored.records[0]["audit_id"]
    assert restored.records[2]["prev_audit_digest"] == restored.records[1]["audit_id"]
    assert deprecated.status == "DEPRECATED"
    assert ANSWER_TEXT not in log_text
    assert QUESTION_TEXT not in log_text
    assert SOURCE_TEXT not in log_text
