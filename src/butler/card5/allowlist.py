from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

EXPECTED_ALLOWLIST_SHA256 = "063b11e7004f113846af24587c1550dcb25820eb518ed4dff9e8679d8d2fe57a"


def compute_sha256_text(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_allowlist(path: Path | None = None) -> dict[str, Any]:
    target = path or Path(__file__).with_name("account_title_allowlist_47.json")
    if not target.exists():
        raise RuntimeError(f"BLOCK: allowlist file not found: {target}")
    actual_sha = compute_sha256_text(target)
    if actual_sha != EXPECTED_ALLOWLIST_SHA256:
        raise RuntimeError(
            "BLOCK: allowlist SHA-256 mismatch: "
            f"expected={EXPECTED_ALLOWLIST_SHA256}, got={actual_sha}"
        )
    data = json.loads(target.read_text(encoding="utf-8"))
    if len(data.get("all_titles", [])) != 47:
        raise RuntimeError(f"BLOCK: allowlist title count mismatch: {len(data.get('all_titles', []))}")
    if len(data.get("all_codes", [])) != 47:
        raise RuntimeError(f"BLOCK: allowlist code count mismatch: {len(data.get('all_codes', []))}")
    return data


def title_to_code_map() -> dict[str, str]:
    data = load_allowlist()
    return dict(zip(data["all_titles"], data["all_codes"]))


def allowed_titles() -> set[str]:
    return set(load_allowlist()["all_titles"])

