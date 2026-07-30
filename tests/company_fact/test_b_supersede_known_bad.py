from __future__ import annotations

import json

import pytest

from butler_pc_core.company_policy.contracts import AdminContext, sha256_text
from butler_pc_core.company_fact.known_bad import compute_known_bad_override_digest
from butler_pc_core.company_fact.storage import CompanyFactStore


@pytest.fixture(autouse=True)
def _register_b_test_admin(_registered_admins_for_company_fact_tests):
    # conftest의 _registered_admins_for_company_fact_tests 가 default RoleRegistry store 를 patch 하고
    # root admin 을 bootstrap 한 뒤 실행된다(인자 의존으로 순서 보장). B 테스트의 admin(admin:b-tests)을
    # 동일 registry 에 ACTIVE admin 으로 등록한다 — 미등록이면 verify_admin_context 가 ADMIN_ROLE_NOT_REGISTERED 로 차단한다.
    from butler_pc_core.company_policy import admin_auth

    store = admin_auth.get_default_role_registry_store()
    root = AdminContext(
        admin_id_digest=sha256_text("company-fact-route-admin"),
        role="admin",
        admin_session_digest=sha256_text("company-fact-route-admin-session"),
        auth_method="tauri_secure_invoke",
    )
    store.upsert_member(actor=root, target_admin_id_digest=sha256_text("admin:b-tests"), role="admin")


def _admin() -> AdminContext:
    return AdminContext(
        admin_id_digest=sha256_text("admin:b-tests"),
        role="admin",
        admin_session_digest=sha256_text("session:b-tests"),
        auth_method="tauri_secure_invoke",
    )


def _candidate_payload(answer="잘못된 답변입니다. 원문 승인 금지 테스트용 문장입니다."):
    return dict(
        category="company_policy",
        question_patterns=["휴가 신청은 어떻게 하나요", "휴가 신청 절차"],
        keywords_required=["휴가"],
        keywords_any=["신청", "절차"],
        answer_runtime_text=answer,
        source="대표 승인 문서",
        source_doc="digest-only fixture",
        verified_at="2026-06-19",
        confidence=0.5,
    )


def test_wrong_deprecate_registers_known_bad_and_blocks_similar_candidate(tmp_path):
    store = CompanyFactStore(root=tmp_path)
    entry, _ = store.save_candidate(**_candidate_payload())
    active, _ = store.approve_candidate(entry.fact_id, _admin())

    deprecated, _ = store.deprecate_fact(active.fact_id, _admin(), reason_code="WRONG")
    assert deprecated.status == "DEPRECATED"

    new_entry, _ = store.save_candidate(**_candidate_payload(answer="수정된 답변입니다. 관리자 override 필요 테스트 문장입니다."))
    new_record = store.load_fact(new_entry.fact_id)
    flags = store.known_bad_flags_for_candidate(new_record)
    assert flags["known_bad_suspected"] is True
    assert flags["match_score"] is not None
    assert flags["matched_keywords_count"] >= 1

    with pytest.raises(Exception) as exc_info:
        store.approve_candidate(new_entry.fact_id, _admin())
    assert "KNOWN_BAD_APPROVAL_BLOCKED" in str(exc_info.value)

    override = store.override_known_bad_candidate(new_entry.fact_id, _admin())
    assert override["raw_text_logged"] is False
    approved, _ = store.approve_candidate(new_entry.fact_id, _admin())
    assert approved.status == "ACTIVE"


def test_supersede_deprecates_old_and_links_previous_digest(tmp_path):
    store = CompanyFactStore(root=tmp_path)
    entry, _ = store.save_candidate(**_candidate_payload(answer="기존 정답입니다. 충분한 길이의 승인 답변입니다."))
    active, _ = store.approve_candidate(entry.fact_id, _admin())
    old = store.load_fact(active.fact_id)

    result = store.supersede_fact(active.fact_id, _candidate_payload(answer="새 정답입니다. 충분한 길이의 교체 답변입니다."), _admin())
    assert result["old_status"] == "DEPRECATED"
    assert result["new_status"] == "ACTIVE"
    assert result["previous_fact_digest"] == old.fact_digest

    old_after = store.load_fact(result["old_fact_id"])
    new_after = store.load_fact(result["new_fact_id"])
    assert old_after.status == "DEPRECATED"
    assert new_after.previous_fact_digest == old.fact_digest


def test_superseeded_deprecate_does_not_register_known_bad(tmp_path):
    store = CompanyFactStore(root=tmp_path)
    entry, _ = store.save_candidate(**_candidate_payload())
    active, _ = store.approve_candidate(entry.fact_id, _admin())
    store.deprecate_fact(active.fact_id, _admin(), reason_code="SUPERSEDED")
    assert store.load_known_bad_entries() == []


def test_malformed_override_record_does_not_clear_suspected_flag(tmp_path):
    store = CompanyFactStore(root=tmp_path)
    entry, _ = store.save_candidate(**_candidate_payload())
    active, _ = store.approve_candidate(entry.fact_id, _admin())
    store.deprecate_fact(active.fact_id, _admin(), reason_code="WRONG")

    new_entry, _ = store.save_candidate(**_candidate_payload(answer="수정된 답변입니다. malformed override 차단 테스트 문장입니다."))
    store.known_bad_override_path.write_text(
        '{"schema_version":"company_fact.known_bad_override_file.v1","overrides":{"%s":{"status":"ACTIVE"}}}' % new_entry.fact_id,
        encoding="utf-8",
    )

    with pytest.raises(Exception) as exc_info:
        store._load_override_data()
    assert "KNOWN_BAD_OVERRIDE_LOAD_FAILED" in str(exc_info.value)

    flags = store.known_bad_flags_for_candidate(store.load_fact(new_entry.fact_id))
    assert flags["known_bad_suspected"] is True
    assert flags["override_active"] is False
    with pytest.raises(Exception) as approve_exc:
        store.approve_candidate(new_entry.fact_id, _admin())
    assert "KNOWN_BAD_APPROVAL_BLOCKED" in str(approve_exc.value)


def test_stale_override_digest_does_not_apply_to_changed_candidate(tmp_path):
    store = CompanyFactStore(root=tmp_path)
    entry, _ = store.save_candidate(**_candidate_payload())
    active, _ = store.approve_candidate(entry.fact_id, _admin())
    store.deprecate_fact(active.fact_id, _admin(), reason_code="WRONG")

    new_entry, _ = store.save_candidate(**_candidate_payload(answer="수정된 답변입니다. stale override 차단 테스트 문장입니다."))
    override = store.override_known_bad_candidate(new_entry.fact_id, _admin())
    override["candidate_fact_digest"] = sha256_text("stale-candidate")
    override["override_digest"] = compute_known_bad_override_digest(override)
    store.known_bad_override_path.write_text(
        '{"schema_version":"company_fact.known_bad_override_file.v1","overrides":{"%s":%s}}'
        % (new_entry.fact_id, json.dumps(override, ensure_ascii=False, sort_keys=True)),
        encoding="utf-8",
    )

    flags = store.known_bad_flags_for_candidate(store.load_fact(new_entry.fact_id))
    assert flags["known_bad_suspected"] is True
    assert flags["override_active"] is False


def test_malformed_known_bad_index_wraps_as_load_failure(tmp_path):
    store = CompanyFactStore(root=tmp_path)
    store.known_bad_index_path.write_text(
        '{"schema_version":"company_fact.known_bad_index_file.v1","entries":{"bad":{"schema_version":"bad"}}}',
        encoding="utf-8",
    )
    with pytest.raises(Exception) as exc_info:
        store.load_known_bad_entries()
    assert "KNOWN_BAD_INDEX_LOAD_FAILED" in str(exc_info.value)
