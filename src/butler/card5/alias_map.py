from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from .allowlist import allowed_titles, title_to_code_map

ALLOWED_TAX_RELEVANCE = {"taxable", "non_taxable", "exempt", "unknown"}

ALIAS_MAP_12: dict[str, str] = {
    "서비스매출": "용역매출",
    "임대수익": "임대료수익",
    "대출이자비용": "이자비용",
    "사무실 월세": "지급임차료",
    "사무실월세": "지급임차료",
    "재고자산상각비": "상품매출원가",
    "원료비": "제품매출원가",
    "제품비": "상품매출원가",
    "하도급원가": "용역원가",
    "개발비": "용역원가",
    "보험수리적손실": "잡손실",
    "용역수익": "용역매출",
    "제품원가": "제품매출원가",
}


@dataclass(frozen=True)
class AliasDecision:
    account_title: str
    account_code: str
    category: str
    reason: str
    rule_order: int | None = None


def load_alias_map(path: str | Path | None = None) -> dict[str, Any]:
    target = Path(path) if path is not None else Path(__file__).with_name("canonical_alias_map.json")
    return json.loads(target.read_text(encoding="utf-8"))


def normalize_rent_account(description: str, predicted: Mapping[str, Any]) -> AliasDecision | None:
    desc = description or ""
    if "임대료수익" in desc:
        return AliasDecision("임대료수익", "9040", "non_operating_income", "description contains 임대료수익", 1)
    if all(token in desc for token in ("일시", "정산", "임대료")):
        return AliasDecision("임대료수익", "9040", "non_operating_income", "description contains 일시+정산+임대료", 2)
    if "영업외" in desc and "임대" in desc:
        return AliasDecision("임대료수익", "9040", "non_operating_income", "description contains 영업외+임대", 3)
    if "임대수입" in desc:
        return AliasDecision("임대수입", "4050", "sales", "description contains 임대수입", 4)
    if "임대매출" in desc:
        return AliasDecision("임대수입", "4050", "sales", "description contains 임대매출", 5)
    if "임대 매출" in desc:
        return AliasDecision("임대수입", "4050", "sales", "description contains 임대 매출", 6)
    if "임차" in desc or "임차료" in desc:
        return AliasDecision("지급임차료", "8120", "sga", "description contains 임차/임차료", 7)
    return None


def apply_canonical_alias_map(description: str, prediction: Mapping[str, Any]) -> dict[str, Any]:
    out = dict(prediction)
    decision = normalize_rent_account(description, prediction)
    if decision is None:
        out["alias_map_applied"] = False
        return out
    out["account_title"] = decision.account_title
    out["account_code"] = decision.account_code
    out["category"] = decision.category
    out["alias_map_applied"] = True
    out["alias_reason"] = decision.reason
    out["alias_rule_order"] = decision.rule_order
    return out


def _description_from_prediction(prediction: Mapping[str, Any]) -> str:
    for key in ("description", "description_redacted", "transaction_description", "input_description", "text"):
        value = prediction.get(key)
        if isinstance(value, str):
            return value
    return ""


def _apply_title_code_alias(predicted_title: Any, predicted_code: Any) -> tuple[str, str, str]:
    title = str(predicted_title or "").strip()
    code = str(predicted_code or "").strip()
    code_map = title_to_code_map()
    titles = allowed_titles()
    if title in titles:
        return title, code_map[title], "exact"
    if title in ALIAS_MAP_12:
        corrected_title = ALIAS_MAP_12[title]
        return corrected_title, code_map[corrected_title], "alias_mapped"
    return title, code, "hallucination"


def _unsupported_dict(original_title: Any = "", original_code: Any = "") -> dict[str, Any]:
    return {
        "account_title": str(original_title or ""),
        "account_code": str(original_code or ""),
        "needs_review": True,
        "alias_applied": False,
        "alias_map_applied": False,
        "alias_fail_class": "UNSUPPORTED_ALIAS_INPUT",
    }


def apply_alias(
    *args: Any,
    description: str | None = None,
    prediction: Mapping[str, Any] | None = None,
    **kwargs: Any,
) -> dict[str, Any] | tuple[str, str, str]:
    """Main-repo compatible Card 5 alias API.

    Dict inputs preserve dict output. Title/code inputs restore the original
    main-repo 3-tuple `(account_title, account_code, match_kind)` contract.
    """
    kwargs.pop("precedence_rules", None)
    if kwargs:
        return _unsupported_dict()

    if len(args) >= 2 and not isinstance(args[1], Mapping):
        return _apply_title_code_alias(args[0], args[1])

    if prediction is not None:
        pred = dict(prediction)
        desc = description if description is not None else _description_from_prediction(pred)
        return apply_canonical_alias_map(str(desc or ""), pred)

    if len(args) == 1 and isinstance(args[0], Mapping):
        pred = dict(args[0])
        desc = description if description is not None else _description_from_prediction(pred)
        return apply_canonical_alias_map(str(desc or ""), pred)

    if len(args) >= 2 and isinstance(args[0], str) and isinstance(args[1], Mapping):
        return apply_canonical_alias_map(args[0], dict(args[1]))

    if len(args) >= 2 and isinstance(args[0], Mapping) and isinstance(args[1], str):
        return apply_canonical_alias_map(args[1], dict(args[0]))

    return _unsupported_dict()


def apply_alias_with_precedence(description: str, prediction: Mapping[str, Any]) -> dict[str, Any]:
    return apply_canonical_alias_map(description, prediction)


def validate_tax_relevance(value: Any) -> str:
    if value in ALLOWED_TAX_RELEVANCE:
        return str(value)
    if value == "vat":
        return "taxable"
    return "unknown"

