from __future__ import annotations

import json

import pytest

from butler_pc_core.company_policy.admin_auth import AdminAuthError, verify_admin_context
from butler_pc_core.company_policy.audit import GLOBAL_ADMIN_AUDIT_STORE
from butler_pc_core.company_policy.contracts import AdminContext, sha256_text
from butler_pc_core.company_policy.storage import CompanyFormatStore
# helper3 format adapter 위치 정합 (표준 156, 박스 3 real adapter 위치): MAINDEV
# `company_policy/format_adapter.py` 위치 폐기, ALG `cards/box3/adapters/company_format_adapter`
# 단일 경로가 정본. 본 테스트의 helper3 케이스(2건) 도 동일 위치 API로 재작성한다.
from butler_pc_core.cards.box3.adapters.company_format_adapter import apply_company_format_runtime


def admin(role="admin"):
    return AdminContext(
        admin_id_digest=sha256_text("admin"),
        role=role,
        admin_session_digest=sha256_text("session"),
        auth_method="tauri_secure_invoke",
    )


def test_admin_auth_rejects_non_admin():
    with pytest.raises(AdminAuthError):
        verify_admin_context(admin("manager"), operation="register_format")


def test_format_registration_admin_only_raw_audit_zero(tmp_path):
    GLOBAL_ADMIN_AUDIT_STORE.clear()
    store = CompanyFormatStore(root=tmp_path / "formats")
    fmt, audit = store.register_format(
        template_runtime_text="제목:\n본문:\n결재:",
        format_kind="report",
        title_runtime_text="표준 보고서",
        language="ko",
        dept_digest=sha256_text("dept"),
        admin=admin(),
    )
    assert fmt.template_ref.startswith("local-vault://")
    assert fmt.template_digest == sha256_text("제목:\n본문:\n결재:")
    encoded = json.dumps(audit, ensure_ascii=False)
    assert "제목:" not in encoded
    assert "표준 보고서" not in encoded
    assert audit["raw_saved_zero"] is True
    assert audit["raw_text_logged"] is False


def test_helper3_format_unregistered_needs_review(tmp_path):
    store = CompanyFormatStore(root=tmp_path / "formats")
    result = apply_company_format_runtime(
        draft_text_runtime_only="draft 본문",
        format_id="missing",
        store=store,
    ).to_dict()
    assert result["format_applied"] is False
    assert result["needs_review"] is True
    assert result["fail_class"] == "FORMAT_NOT_REGISTERED"


def test_helper3_format_registered_digest_only(tmp_path):
    store = CompanyFormatStore(root=tmp_path / "formats")
    fmt, _ = store.register_format(
        template_runtime_text="양식 원문은 암호화 저장",
        format_kind="report",
        title_runtime_text="보고서",
        language="ko",
        dept_digest=sha256_text("dept"),
        admin=admin(),
    )
    result = apply_company_format_runtime(
        draft_text_runtime_only="초안 본문(runtime only)",
        format_id=fmt.format_id,
        store=store,
    ).to_dict()
    encoded = json.dumps(result, ensure_ascii=False)
    assert result["format_applied"] is True
    assert result["needs_review"] is False
    # 결과 payload 는 digest-only — 원문(template/draft) 평문 노출 0.
    assert "양식 원문" not in encoded
    assert "초안 본문" not in encoded
    assert result["template_digest"] == fmt.template_digest
    assert result["format_digest"] == fmt.format_digest
    assert result["formatted_digest"].startswith("sha256:")
    assert result["external_send_zero"] is True
    assert result["raw_saved_zero"] is True
