"""Card 5 v3 system prompt."""
from __future__ import annotations

from .allowlist import load_allowlist

V3_SYSTEM_PROMPT_TEMPLATE = """당신은 한국 회계 분류 보조 모델입니다.

아래 47개 계정과목 중 하나만 account_title로 출력해야 합니다.

{categories}

ABSOLUTE RULES:
1. account_title은 반드시 위 47개 정확 명칭 중 하나여야 합니다.
2. account_code는 account_title과 1:1로 정합해야 합니다.
3. 출력은 JSON 객체 하나만 허용합니다.
4. 모호한 거래, 세무·법률 판단이 필요한 거래는 needs_review=true로 표시합니다.
5. 47개 밖 계정과목을 만들지 않습니다.

거래 내역:
{transaction}
"""


def _format_categories(allowlist: dict) -> str:
    rows: list[str] = []
    categories = allowlist.get("categories", {})

    for category, items in categories.items():
        names: list[str] = []
        for item in items:
            if isinstance(item, dict):
                names.append(str(item["name"]))
            else:
                names.append(str(item))
        rows.append(f"- {category}: " + ", ".join(names))

    return "\n".join(rows)


def build_system_prompt(transaction: str) -> str:
    allowlist = load_allowlist()
    return V3_SYSTEM_PROMPT_TEMPLATE.format(
        categories=_format_categories(allowlist),
        transaction=transaction,
    )
