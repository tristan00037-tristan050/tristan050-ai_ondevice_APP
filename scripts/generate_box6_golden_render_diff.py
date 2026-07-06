#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import yaml


BASELINE_SHA = "42971a1da499b00e38f20f0a1ccefe376064cf35"
CARD_PATHS = {
    "2": "butler_pc_core/prompts/cards/card_02_external_to_our_format.yaml",
    "3": "butler_pc_core/prompts/cards/card_03_new_draft_from_past.yaml",
    "5": "butler_pc_core/prompts/cards/card_05_bank_to_accounting.yaml",
}


def _fail(code: str) -> None:
    print("BOX6_GOLDEN_RENDER_DIFF_GENERATED=0")
    print(f"ERROR_CODE={code}")
    raise SystemExit(1)


def _sha256_text(text: str) -> str:
    return "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()


def _semantic(text: str) -> str:
    return " ".join(text.split())


def _git_show(root: Path, ref_path: str) -> str:
    try:
        return subprocess.check_output(
            ["git", "show", ref_path],
            cwd=root,
            text=True,
            stderr=subprocess.DEVNULL,
        )
    except Exception:
        _fail("BASELINE_SOURCE_UNAVAILABLE")


def _git_head(root: Path) -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
            cwd=root,
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
    except Exception:
        _fail("HEAD_SHA_UNAVAILABLE")


def _load_current_renderer(root: Path):
    sys.path.insert(0, str(root))
    from butler_pc_core.prompts.card_renderer import render_card_user_prompt
    from butler_pc_core.prompts.cards import load_card_prompt

    return render_card_user_prompt, load_card_prompt


def _load_baseline_renderer(root: Path):
    source = _git_show(root, f"{BASELINE_SHA}:butler_pc_core/prompts/card_renderer.py")
    namespace: dict[str, Any] = {"__name__": "box6_baseline_card_renderer"}
    exec(compile(source, "baseline_card_renderer.py", "exec"), namespace)
    return namespace["render_card_user_prompt"]


def _baseline_card(root: Path, mode: str) -> dict[str, Any]:
    raw = _git_show(root, f"{BASELINE_SHA}:{CARD_PATHS[mode]}")
    data = yaml.safe_load(raw)
    if not isinstance(data, dict):
        _fail("BASELINE_CARD_INVALID")
    return data


def _write_diff(root: Path, output_dir: Path, mode: str) -> None:
    current_render, current_card_loader = _load_current_renderer(root)
    baseline_render = _load_baseline_renderer(root)
    query = f"카드 {mode} 본문"
    files = ["첨부 자료"]
    baseline = baseline_render(_baseline_card(root, mode), query=query, file_texts=files)
    current = current_render(current_card_loader(mode), query=query, file_texts=files)
    payload = {
        "schema_version": "box6.golden_render_diff.v1",
        "card_mode": mode,
        "baseline_sha": BASELINE_SHA,
        "head_sha": _git_head(root),
        "baseline_render_sha256": _sha256_text(baseline),
        "head_render_sha256": _sha256_text(current),
        "baseline_semantic_sha256": _sha256_text(_semantic(baseline)),
        "head_semantic_sha256": _sha256_text(_semantic(current)),
        "byte_diff_zero": baseline == current,
        "semantic_diff_zero": _semantic(baseline) == _semantic(current),
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / f"card_{mode}_render_diff.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("root", nargs="?", default=".")
    parser.add_argument("output_dir", nargs="?", default="evidence/box6/contract_fixture/golden")
    args = parser.parse_args()
    root = Path(args.root).resolve()
    output_dir = Path(args.output_dir)
    if not output_dir.is_absolute():
        output_dir = root / output_dir
    for mode in sorted(CARD_PATHS):
        _write_diff(root, output_dir, mode)
    print("BOX6_GOLDEN_RENDER_DIFF_GENERATED=1")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
