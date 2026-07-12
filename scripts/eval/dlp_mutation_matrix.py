#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from butler_pc_core.cards.box3.security import scan_forbidden_text
from butler_pc_core.cards.box4.review_service import _require_string as box4_require_string
from butler_pc_core.cards.box6.form_fill_service import _require_string as box6_require_string
from butler_pc_core.dlp import scan_runtime


BASE_CASES = {
    "email": ("alice1@example.com", "PII_EMAIL"),
    "phone": ("010-1234-5678", "PII_PHONE"),
    "korean_rrn": ("900101-1234567", "PII_KOREAN_RRN"),
    "card_or_account": ("4111 1111 1111 1111", "PII_CARD_OR_ACCOUNT"),
    "secret": ("token: abcdefghijklmno1", "SECRET"),
    "local_path": ("/Users/person/private1.txt", "LOCAL_PATH"),
}


def _insert_after_first(text: str, marker: str) -> str:
    return text[:1] + marker + text[1:]


def _fullwidth(text: str) -> str:
    return "".join(chr(ord(char) + 0xFEE0) if 0x21 <= ord(char) <= 0x7E else "\u3000" if char == " " else char for char in text)


def _enclose_first_ascii_alnum(text: str) -> str:
    circled = {**{chr(65 + i): chr(0x24B6 + i) for i in range(26)}, **{chr(97 + i): chr(0x24D0 + i) for i in range(26)}}
    circled.update({str(i): chr(0x2460 + i - 1) for i in range(1, 10)})
    for index, char in enumerate(text):
        if char in circled:
            return text[:index] + circled[char] + text[index + 1 :]
    return text


def _keycap_digits(text: str) -> str:
    return "".join(char + "\ufe0f\u20e3" if char.isascii() and char.isdigit() else char for char in text)


def _arabic_indic_digits(text: str) -> str:
    return "".join(chr(0x0660 + int(char)) if char.isascii() and char.isdigit() else char for char in text)


MUTATIONS = {
    "zero_width": lambda text: _insert_after_first(text, "\u200b"),
    "fullwidth_nfkc": _fullwidth,
    "visual_noise": lambda text: _insert_after_first(text, "😀"),
    "variation_selector": lambda text: _insert_after_first(text, "\ufe0f"),
    "enclosed_compatibility": _enclose_first_ascii_alnum,
    "keycap_noise": _keycap_digits,
    "unicode_decimal": _arabic_indic_digits,
    "mixed_nfkc_zero_width": lambda text: _insert_after_first(_fullwidth(text), "\u2060"),
    "mixed_visual_decimal": lambda text: _insert_after_first(_arabic_indic_digits(text), "🔒"),
}


def main() -> int:
    failures: list[str] = []
    checks = 0
    for category, (base, reason_code) in BASE_CASES.items():
        for mutation_name, mutate in MUTATIONS.items():
            value = mutate(base)
            checks += 1
            result = scan_runtime(value)
            if category not in {item.category for item in result.findings}:
                failures.append(f"FACADE:{category}:{mutation_name}")
            for card_name, adapter in (
                ("box3", lambda text: reason_code in scan_forbidden_text(text)),
                ("box4", lambda text: box4_require_string(text, "INVALID", max_len=20_000) != text),
                ("box6", lambda text: box6_require_string(text, "INVALID", max_len=20_000) != text),
            ):
                checks += 1
                try:
                    if not adapter(value):
                        failures.append(f"{card_name}:{category}:{mutation_name}")
                except Exception:
                    failures.append(f"{card_name}:{category}:{mutation_name}")

    print(f"DLP_STANDARD_MUTATION_OK={0 if failures else 1}")
    print(
        json.dumps(
            {
                "schema_version": "butler.dlp_mutation_matrix.v1",
                "mutation_types": len(MUTATIONS),
                "categories": len(BASE_CASES),
                "checks_passed": checks - len(failures),
                "checks_total": checks,
                "raw_text_logged": False,
            },
            sort_keys=True,
        )
    )
    for failure in failures:
        print(f"ERROR_CODE=MUTATION_MISSED:{failure}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
