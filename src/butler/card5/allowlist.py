"""Card 5 47 계정과목 allowlist loader.

본 EXPECTED_ALLOWLIST_SHA256 은 본 main 본 정착된 allowlist 본문 파일 본 실
SHA-256이다. 본문 내장 `allowlist_sha256` 필드(`16b5403e…`)는 박스 v2.6 시점
self-reference 봉인 본질이며, 본 fail-closed 본 본 본 본문 SHA(byte 단위)와
비교한다.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

EXPECTED_ALLOWLIST_SHA256 = "063b11e7004f113846af24587c1550dcb25820eb518ed4dff9e8679d8d2fe57a"

ALLOWLIST_PATH = (
    Path(__file__).resolve().parents[3]
    / "evidence/accounting27/account_title_allowlist_47.json"
)


def compute_sha256_text(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_allowlist(path: Path = ALLOWLIST_PATH) -> dict:
    if not path.exists():
        raise RuntimeError(f"BLOCK: allowlist file not found: {path}")

    actual_sha = compute_sha256_text(path)
    if actual_sha != EXPECTED_ALLOWLIST_SHA256:
        raise RuntimeError(
            "BLOCK: allowlist SHA-256 mismatch: "
            f"expected={EXPECTED_ALLOWLIST_SHA256}, got={actual_sha}"
        )

    data = json.loads(path.read_text(encoding="utf-8"))

    titles = data.get("all_titles", [])
    codes = data.get("all_codes", [])

    if len(titles) != 47:
        raise RuntimeError(f"BLOCK: allowlist title count mismatch: {len(titles)}")
    if len(codes) != 47:
        raise RuntimeError(f"BLOCK: allowlist code count mismatch: {len(codes)}")

    return data


def title_to_code_map() -> dict[str, str]:
    data = load_allowlist()
    titles = data["all_titles"]
    codes = data["all_codes"]
    return dict(zip(titles, codes))


def allowed_titles() -> set[str]:
    return set(load_allowlist()["all_titles"])
