from __future__ import annotations

import json

import pytest

from butler_pc_core.accounting.format_kinds import (
    ACCOUNTING_FORMAT_KINDS,
    is_accounting_format_kind,
)
from butler_pc_core.accounting.report import (
    apply_company_format_to_report,
    should_block_requested_accounting_format,
)
from butler_pc_core.company_policy.contracts import (
    AdminContext,
    ContractValidationError,
    FORMAT_KIND_VALUES,
    make_company_format,
    sha256_text,
)
from butler_pc_core.company_policy.storage import CompanyFormatStore


def _admin() -> AdminContext:
    return AdminContext(
        admin_id_digest=sha256_text("accounting-format-admin"),
        role="admin",
        admin_session_digest=sha256_text("accounting-format-session"),
        auth_method="test_only",
    )


def _register_format(
    store: CompanyFormatStore,
    *,
    template: str,
    kind: str,
    title: str = "테스트 양식",
):
    fmt, _audit = store.register_format(
        template_runtime_text=template,
        format_kind=kind,
        title_runtime_text=title,
        language="ko",
        dept_digest=sha256_text("dept-accounting"),
        admin=_admin(),
    )
    return fmt


def test_accounting_company_format_cash_flow_monthly_applies_report_runtime_text(tmp_path):
    store = CompanyFormatStore(root=tmp_path / "formats")
    fmt = _register_format(
        store,
        template="=== 우리회사 월간 현금흐름 ===\n{draft}\n=== 끝 ===",
        kind="cash_flow_monthly",
        title="우리회사 월간 현금흐름",
    )
    report = "## 회계 분류 결과 요약\n\n- 총 거래건수: 1건"

    result = apply_company_format_to_report(report, fmt.format_id, store=store)
    payload = result.application.to_dict()

    assert result.report_text_runtime.startswith("=== 우리회사 월간 현금흐름 ===")
    assert report in result.report_text_runtime
    assert result.report_text_runtime.endswith("=== 끝 ===")
    assert payload["format_applied"] is True
    assert payload["needs_review"] is False
    assert payload["formatted_digest"] == sha256_text(result.report_text_runtime)
    assert payload["format_digest"] == fmt.format_digest
    assert payload["template_digest"] == fmt.template_digest


def test_accounting_company_format_missing_format_id_preserves_report(tmp_path):
    store = CompanyFormatStore(root=tmp_path / "formats")
    report = "기본 회계 리포트"

    result = apply_company_format_to_report(report, None, store=store)

    assert result.report_text_runtime == report
    assert result.application.to_dict()["format_applied"] is False
    assert result.application.to_dict()["fail_class"] == "FORMAT_ID_MISSING"


def test_accounting_company_format_unregistered_preserves_report(tmp_path):
    store = CompanyFormatStore(root=tmp_path / "formats")
    report = "기본 회계 리포트"

    result = apply_company_format_to_report(report, "format-missing", store=store)

    assert result.report_text_runtime == report
    assert result.application.to_dict()["format_applied"] is False
    assert result.application.to_dict()["fail_class"] == "FORMAT_NOT_REGISTERED"


@pytest.mark.parametrize("kind", ["report", "official_letter"])
def test_accounting_company_format_rejects_document_format_kind(tmp_path, kind):
    store = CompanyFormatStore(root=tmp_path / "formats")
    fmt = _register_format(store, template="문서 양식\n{draft}", kind=kind)
    report = "기본 회계 리포트"

    result = apply_company_format_to_report(report, fmt.format_id, store=store)
    payload = result.application.to_dict()

    assert result.report_text_runtime == report
    assert payload["format_applied"] is False
    assert payload["fail_class"] == "ACCOUNTING_FORMAT_KIND_MISMATCH"
    assert payload["format_digest"] == fmt.format_digest
    assert payload["template_digest"] == fmt.template_digest


def test_accounting_company_format_application_payload_is_digest_only(tmp_path):
    store = CompanyFormatStore(root=tmp_path / "formats")
    template = "회계 양식 원문 {draft}"
    report = "거래 row runtime text와 총 거래건수"
    fmt = _register_format(store, template=template, kind="pnl_summary")

    result = apply_company_format_to_report(report, fmt.format_id, store=store)
    encoded = json.dumps(result.application.to_dict(), ensure_ascii=False, sort_keys=True)

    assert template not in encoded
    assert report not in encoded
    assert "template_runtime_text" not in encoded
    assert "file_path" not in encoded
    assert "row_text" not in encoded
    assert "draft_text" not in encoded
    assert result.application.to_dict()["formatted_digest"].startswith("sha256:")
    assert result.application.to_dict()["external_send_zero"] is True
    assert result.application.to_dict()["raw_saved_zero"] is True


def test_accounting_company_format_kind_contract_is_append_only(tmp_path):
    assert {"report", "freeform"}.issubset(FORMAT_KIND_VALUES)
    assert ACCOUNTING_FORMAT_KINDS.issubset(FORMAT_KIND_VALUES)
    assert is_accounting_format_kind("cash_flow_daily") is True
    assert is_accounting_format_kind("report") is False

    store = CompanyFormatStore(root=tmp_path / "formats")
    report_fmt = _register_format(store, template="보고서 {draft}", kind="report")
    freeform_fmt = _register_format(store, template="자유형 {draft}", kind="freeform")

    assert report_fmt.format_kind == "report"
    assert freeform_fmt.format_kind == "freeform"
    with pytest.raises(ContractValidationError):
        make_company_format(
            format_kind="not_a_valid_format_kind",
            template_ref="local-vault://formats/templates/template-invalid",
            template_digest=sha256_text("template"),
            metadata={
                "title_digest": sha256_text("title"),
                "language": "ko",
                "dept_digest": sha256_text("dept-accounting"),
            },
            registered_by_digest=_admin().admin_id_digest,
        )


def test_requested_unusable_accounting_format_is_blocking_decision(tmp_path):
    store = CompanyFormatStore(root=tmp_path / "formats")
    report = "기본 회계 리포트"

    missing = apply_company_format_to_report(report, "format-missing", store=store)
    not_requested = apply_company_format_to_report(report, None, store=store)

    assert missing.application.to_dict()["fail_class"] == "FORMAT_NOT_REGISTERED"
    assert should_block_requested_accounting_format("format-missing", missing.application) is True
    assert should_block_requested_accounting_format(None, not_requested.application) is False
