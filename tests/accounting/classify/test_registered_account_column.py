from __future__ import annotations

import pytest

from butler_pc_core.accounting.classify.account_column import (
    AccountAliasRegistry,
    AccountColumnCompiler,
    AccountColumnContractError,
    AccountColumnReason,
    AccountColumnState,
    AccountRegistryEntry,
    AccountRegistrySnapshot,
    HeaderResolutionStatus,
    SourceCell,
    SourceCellKind,
)

from .conftest import digest


def _registry(*extra: AccountRegistryEntry) -> AccountRegistrySnapshot:
    return AccountRegistrySnapshot(
        registry_digest=digest("registered-info-registry"),
        overlay_digest=digest("registered-info-overlay"),
        locale="ko-KR",
        entries=(
            AccountRegistryEntry("PL.SGA.ADVERTISING", "5100", "광고 선전비", True),
            AccountRegistryEntry("PL.SGA.PAYMENT_FEE", "5200", "지급 수수료", True),
            AccountRegistryEntry(
                "PL.SGA.GROUP", None, "판매관리비", False, "GROUP_NODE"
            ),
            *extra,
        ),
    )


def _compiler(*extra: AccountRegistryEntry) -> AccountColumnCompiler:
    aliases = AccountAliasRegistry(
        locale="ko-KR",
        version="account-aliases-v1",
        aliases=("account_id", "account_code", "계정과목", "계정코드", "계정명"),
    )
    return AccountColumnCompiler(aliases, _registry(*extra))


def _header(value: str, column: int = 2, coordinate: str = "C1") -> SourceCell:
    return SourceCell(column, coordinate, SourceCellKind.TEXT, value)


def _resolve(compiler: AccountColumnCompiler, value: str, *, kind=SourceCellKind.TEXT):
    header = compiler.detect_header((_header("계정과목"),))
    return compiler.resolve_cell(
        header,
        SourceCell(2, "C2", kind, value),
        source_file_digest=digest("source-file"),
        sheet_id="sheet-001",
        table_id="table-001",
    )


def test_header_uses_exact_normalized_alias_only():
    compiler = _compiler()
    result = compiler.detect_header((_header("  ACCOUNT_ID  "),))
    assert result.status is HeaderResolutionStatus.SELECTED
    assert result.selected_column == 2
    assert (
        compiler.detect_header((_header("계정 과목"),)).status
        is HeaderResolutionStatus.NOT_FOUND
    )
    assert (
        compiler.detect_header((_header("추천 계정과목"),)).status
        is HeaderResolutionStatus.NOT_FOUND
    )


def test_multiple_exact_header_candidates_require_explicit_mapping():
    compiler = _compiler()
    headers = (_header("계정코드", 1, "B1"), _header("계정명", 3, "D1"))
    unresolved = compiler.detect_header(headers)
    assert unresolved.status is HeaderResolutionStatus.SELECTION_REQUIRED
    assert unresolved.candidate_columns == (1, 3)
    selected = compiler.detect_header(headers, selected_column=3)
    assert selected.status is HeaderResolutionStatus.SELECTED
    assert selected.header_coordinate == "D1"
    with pytest.raises(
        AccountColumnContractError, match="ACCOUNT_COLUMN_SELECTION_INVALID"
    ):
        compiler.detect_header(headers, selected_column=2)


@pytest.mark.parametrize(
    ("value", "account_id", "reason"),
    [
        (
            "PL.SGA.ADVERTISING",
            "PL.SGA.ADVERTISING",
            AccountColumnReason.SOURCE_ACCOUNT_EXACT_ID,
        ),
        ("5200", "PL.SGA.PAYMENT_FEE", AccountColumnReason.SOURCE_ACCOUNT_EXACT_CODE),
        (
            "  광고   선전비 ",
            "PL.SGA.ADVERTISING",
            AccountColumnReason.SOURCE_ACCOUNT_EXACT_NAME,
        ),
    ],
)
def test_cell_resolution_priority_is_id_then_code_then_unique_name(
    value, account_id, reason
):
    resolved = _resolve(_compiler(), value)
    assert resolved.state is AccountColumnState.SOURCE_DECLARED_VALID
    assert resolved.account_id == account_id
    assert resolved.reason is reason
    assert resolved.receipt is not None
    assert resolved.receipt.resolved_account_id == account_id


def test_unknown_and_nonassignable_cells_stay_review_required():
    unknown = _resolve(_compiler(), "광고비 비슷한 이름")
    assert unknown.state is AccountColumnState.REVIEW_REQUIRED
    assert unknown.reason is AccountColumnReason.SOURCE_ACCOUNT_UNKNOWN
    group = _resolve(_compiler(), "PL.SGA.GROUP")
    assert group.state is AccountColumnState.REVIEW_REQUIRED
    assert group.reason is AccountColumnReason.SOURCE_ACCOUNT_NONASSIGNABLE


def test_duplicate_normalized_display_name_never_chooses_one():
    duplicate = AccountRegistryEntry(
        "PL.SGA.ADVERTISING.OTHER", "5101", "광고   선전비", True
    )
    result = _resolve(_compiler(duplicate), "광고 선전비")
    assert result.state is AccountColumnState.REVIEW_REQUIRED
    assert result.reason is AccountColumnReason.SOURCE_ACCOUNT_DUPLICATE_NAME


@pytest.mark.parametrize(
    ("kind", "value", "reason"),
    [
        (
            SourceCellKind.FORMULA,
            "=A1",
            AccountColumnReason.SOURCE_ACCOUNT_FORMULA_OR_ERROR,
        ),
        (
            SourceCellKind.ERROR,
            "#VALUE!",
            AccountColumnReason.SOURCE_ACCOUNT_FORMULA_OR_ERROR,
        ),
        (
            SourceCellKind.TEXT,
            '=HYPERLINK("x")',
            AccountColumnReason.SOURCE_ACCOUNT_FORMULA_OR_ERROR,
        ),
        (SourceCellKind.NUMBER, "5100", AccountColumnReason.SOURCE_ACCOUNT_NON_TEXT),
    ],
)
def test_formula_error_injection_and_non_text_are_not_mapped(kind, value, reason):
    result = _resolve(_compiler(), value, kind=kind)
    assert result.state is AccountColumnState.REVIEW_REQUIRED
    assert result.reason is reason


def test_no_account_header_is_an_explicit_absent_result():
    compiler = _compiler()
    header = compiler.detect_header((_header("거래처"), _header("금액", 3, "D1")))
    result = compiler.resolve_cell(
        header,
        None,
        source_file_digest=digest("source-file"),
        sheet_id="sheet-001",
    )
    assert result.state is AccountColumnState.ABSENT
    assert result.account_id is None
    assert result.receipt is None


def test_receipt_is_digest_only_and_does_not_echo_raw_cell():
    raw = "광고 선전비"
    result = _resolve(_compiler(), raw)
    receipt = result.receipt
    assert receipt is not None
    mapping = receipt.to_mapping()
    assert raw not in str(mapping)
    assert "raw_value" not in mapping
    assert (
        mapping["cell_raw_digest"]
        == SourceCell(2, "C2", SourceCellKind.TEXT, raw).raw_digest
    )
    assert len(receipt.digest) == 64


def test_source_cell_and_result_repr_do_not_leak_raw_value():
    raw = "민감한 내부 계정 표기"
    cell = SourceCell(2, "C2", SourceCellKind.TEXT, raw)
    assert raw not in repr(cell)


def test_registry_rejects_duplicate_ids_and_codes():
    with pytest.raises(
        AccountColumnContractError, match="REGISTRY_DUPLICATE_ACCOUNT_ID"
    ):
        AccountRegistrySnapshot(
            digest("registry"),
            digest("overlay"),
            "ko-KR",
            (
                AccountRegistryEntry("PL.DUP", "100", "첫째", True),
                AccountRegistryEntry("PL.DUP", "101", "둘째", True),
            ),
        )
    with pytest.raises(
        AccountColumnContractError, match="REGISTRY_DUPLICATE_ACCOUNT_CODE"
    ):
        AccountRegistrySnapshot(
            digest("registry"),
            digest("overlay"),
            "ko-KR",
            (
                AccountRegistryEntry("PL.ONE", "100", "첫째", True),
                AccountRegistryEntry("PL.TWO", "100", "둘째", True),
            ),
        )


def test_alias_digest_is_order_independent_but_version_bound():
    first = AccountAliasRegistry("ko-KR", "v1", ("계정명", "account_id"))
    reordered = AccountAliasRegistry("ko-KR", "v1", ("account_id", "계정명"))
    upgraded = AccountAliasRegistry("ko-KR", "v2", ("계정명", "account_id"))
    assert first.digest == reordered.digest
    assert first.digest != upgraded.digest
