"""LLM 보고서 생성기 + 환각 검증."""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any, Callable

from butler_pc_core.accounting.format_kinds import is_accounting_format_kind
from butler_pc_core.cards.box3.adapters.company_format_adapter import CompanyFormatApplication
from butler_pc_core.company_policy.contracts import sha256_text
from butler_pc_core.company_policy.storage import CompanyFormatStore
from butler_pc_core.company_policy.vault import VaultError

try:
    import pandas as pd
    _PANDAS_OK = True
except ImportError:
    _PANDAS_OK = False

# 시스템 프롬프트: 입력 JSON에 없는 수치·카테고리 언급 금지
_SYSTEM_PROMPT = """당신은 회계 분석 보조 AI입니다.
아래 JSON 요약만을 근거로 짧은 회계 분류 보고서를 작성하세요.

규칙:
1. JSON에 없는 수치(금액, 건수, 비율)를 절대 언급하지 마세요.
2. JSON에 없는 계정과목 이름을 절대 언급하지 마세요.
3. 분석 기간, 거래처 이름 등 JSON에 없는 정보를 추측하지 마세요.
4. 마크다운 형식으로 작성하세요 (## 소제목, 표 사용 권장).
5. 총 500자 이내로 간결하게 작성하세요."""


def build_summary(df: "pd.DataFrame") -> dict[str, Any]:
    """분류 결과 DataFrame → JSON 요약 dict.

    반환 구조:
    {
        "total_rows": int,
        "classified_rows": int,
        "unclassified_rows": int,
        "categories": {
            "급여": {"count": N, "avg_confidence": 0.95, "total_amount": M,
                     "sign": "-", "section": "IV_sga"},
            ...
        },
        "avg_confidence": float,
    }
    """
    if not _PANDAS_OK:
        raise ImportError("pandas가 설치되지 않았습니다.")

    total = len(df)
    if "분류과목" not in df.columns:
        return {"total_rows": total, "classified_rows": 0, "unclassified_rows": total,
                "categories": {}, "guarded_rows": {}, "avg_confidence": 0.0}

    guarded_mask = (
        df.get("_pnl_excluded", False).eq(True)
        if "_pnl_excluded" in df.columns
        else df["분류과목"].map(lambda _value: False)
    )
    unclassified_mask = (df["분류과목"] == "미분류") | guarded_mask
    classified = int((~unclassified_mask).sum())
    unclassified = int(unclassified_mask.sum())
    guarded_rows: dict[str, int] = {}
    if "_guard_reason" in df.columns:
        reasons = df.loc[guarded_mask, "_guard_reason"].fillna("").astype(str)
        guarded_rows = {
            reason: int(count)
            for reason, count in reasons[reasons != ""].value_counts().sort_index().items()
        }

    from .account_dict import ACCOUNT_BY_NAME

    categories: dict[str, Any] = {}
    for name, group in df[~unclassified_mask].groupby("분류과목"):
        conf_col = group["신뢰도"] if "신뢰도" in group.columns else None
        avg_conf = float(conf_col.mean()) if conf_col is not None else 0.0
        # _amt: classify_df가 입출금 분리 컬럼에서 미리 계산한 순액 (없으면 0)
        total_amt = int(group["_amt"].sum()) if "_amt" in group.columns else 0
        # sign/section 메타 — UI 구분 배지([수익]/[비용]) 노출용 (PR #693 정합)
        acc = ACCOUNT_BY_NAME.get(str(name))
        if acc is not None:
            sign, section = acc.sign, acc.section
        else:
            # 사전 미등록 카테고리(PEFT 모델 반환 등) — _amt 순액 부호로
            # 추론한다. 기본값 "+"는 비용 항목을 [수익]으로 오표시할
            # 위험이 있어, 음수 순액은 비용으로 정정한다 (Codex P2).
            sign = "-" if total_amt < 0 else "+"
            section = "expense" if total_amt < 0 else "revenue"
        categories[str(name)] = {
            "count": int(len(group)),
            "avg_confidence": round(avg_conf, 3),
            "total_amount": total_amt,
            "sign": sign,
            "section": section,
        }

    overall_conf = float(df["신뢰도"].mean()) if "신뢰도" in df.columns else 0.0

    return {
        "total_rows": total,
        "classified_rows": classified,
        "unclassified_rows": unclassified,
        "guarded_rows": guarded_rows,
        "categories": categories,
        "avg_confidence": round(overall_conf, 3),
    }


@dataclass(frozen=True)
class AccountingReportFormatResult:
    report_text_runtime: str
    application: CompanyFormatApplication


def _format_not_applied(
    *,
    report_text_runtime: str,
    format_id: str | None,
    fail_class: str,
    format_digest: str | None = None,
    template_digest: str | None = None,
) -> AccountingReportFormatResult:
    return AccountingReportFormatResult(
        report_text_runtime=report_text_runtime,
        application=CompanyFormatApplication(
            format_id=format_id,
            format_applied=False,
            needs_review=True,
            formatted_digest=None,
            format_digest=format_digest,
            template_digest=template_digest,
            fail_class=fail_class,
        ),
    )


def apply_company_format_to_report(
    report_text_runtime: str,
    format_id: str | None,
    store: CompanyFormatStore | None = None,
) -> AccountingReportFormatResult:
    """Apply a registered accounting company format to an in-memory report.

    The plaintext report and template stay runtime-only. Persistable output is
    limited to CompanyFormatApplication digests and fail_class metadata.
    """
    if not format_id:
        return _format_not_applied(
            report_text_runtime=report_text_runtime,
            format_id=None,
            fail_class="FORMAT_ID_MISSING",
        )

    format_store = store or CompanyFormatStore()
    try:
        company_format = format_store.get_format(format_id)
    except Exception:
        return _format_not_applied(
            report_text_runtime=report_text_runtime,
            format_id=format_id,
            fail_class="FORMAT_STORE_LOAD_FAILED",
        )
    if company_format is None or company_format.status != "ACTIVE":
        return _format_not_applied(
            report_text_runtime=report_text_runtime,
            format_id=format_id,
            fail_class="FORMAT_NOT_REGISTERED",
        )

    if not is_accounting_format_kind(company_format.format_kind):
        return _format_not_applied(
            report_text_runtime=report_text_runtime,
            format_id=format_id,
            fail_class="ACCOUNTING_FORMAT_KIND_MISMATCH",
            format_digest=company_format.format_digest,
            template_digest=company_format.template_digest,
        )

    try:
        template_runtime = format_store.load_template_runtime_only(company_format)
    except VaultError as exc:
        return _format_not_applied(
            report_text_runtime=report_text_runtime,
            format_id=format_id,
            fail_class=str(exc),
            format_digest=company_format.format_digest,
            template_digest=company_format.template_digest,
        )
    except Exception:
        return _format_not_applied(
            report_text_runtime=report_text_runtime,
            format_id=format_id,
            fail_class="FORMAT_TEMPLATE_LOAD_FAILED",
            format_digest=company_format.format_digest,
            template_digest=company_format.template_digest,
        )

    formatted_runtime = (
        template_runtime.replace("{draft}", report_text_runtime)
        if "{draft}" in template_runtime
        else f"{template_runtime}\n\n{report_text_runtime}"
    )
    return AccountingReportFormatResult(
        report_text_runtime=formatted_runtime,
        application=CompanyFormatApplication(
            format_id=format_id,
            format_applied=True,
            needs_review=False,
            formatted_digest=sha256_text(formatted_runtime),
            format_digest=company_format.format_digest,
            template_digest=company_format.template_digest,
            fail_class=None,
        ),
    )


def should_block_requested_accounting_format(
    format_id: str | None,
    application: CompanyFormatApplication,
) -> bool:
    """Requested accounting formats must fail closed when unusable.

    No format_id means the caller did not request company-format application,
    so the base accounting report may complete normally.
    """
    return bool(format_id) and not application.format_applied


def validate_report(report_text: str, summary: dict[str, Any]) -> list[str]:
    """보고서에서 summary에 없는 수치를 추출해 반환 (환각 탐지).

    Returns:
        list of suspicious numbers found in report but not in summary JSON.
        빈 리스트 → 환각 없음.
    """
    summary_str = json.dumps(summary, ensure_ascii=False)
    # summary의 모든 숫자 추출
    summary_numbers = set(re.findall(r'\b\d+(?:\.\d+)?\b', summary_str))

    # 보고서의 모든 숫자 추출
    report_numbers = set(re.findall(r'\b\d+(?:\.\d+)?\b', report_text))

    # 보고서에는 있지만 summary에 없는 숫자
    suspicious = sorted(report_numbers - summary_numbers)
    return suspicious


def generate_report(
    summary: dict[str, Any],
    llm_generate: Callable[[str, str], str],
) -> str:
    """LLM 호출 → 자연어 보고서 생성.

    Args:
        summary: build_summary()의 반환값
        llm_generate: (system_prompt, user_content) → str 콜러블

    Returns:
        마크다운 보고서 텍스트
    """
    user_content = f"다음 회계 분류 결과를 보고서로 작성하세요:\n\n```json\n{json.dumps(summary, ensure_ascii=False, indent=2)}\n```"
    report = llm_generate(_SYSTEM_PROMPT, user_content)
    return report.strip()
