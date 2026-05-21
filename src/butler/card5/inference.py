"""Card 5 v3 inference pipeline."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Callable

from .adapter_loader import verify_and_locate_adapter
from .alias_map import apply_alias
from .invariants import REQUIRED_INVARIANTS, verify_invariants
from .rollback import InferenceResult, check_and_rollback
from .system_prompt import build_system_prompt


MlxRunner = Callable[[str, Path], str]


def run_inference(transaction: str, mlx_runner: MlxRunner) -> InferenceResult:
    if mlx_runner is None:
        raise RuntimeError("BLOCK: mlx_runner is required")

    verify_invariants(REQUIRED_INVARIANTS)
    adapter_path = verify_and_locate_adapter()

    prompt = build_system_prompt(transaction)
    raw_output = mlx_runner(prompt, adapter_path)

    try:
        parsed = json.loads(raw_output)
    except json.JSONDecodeError as e:
        raise RuntimeError(f"BLOCK: invalid JSON output: {e}") from e

    # P1 #1 정정 (codex bot review): JSON 타입 검증
    if not isinstance(parsed, dict):
        raise RuntimeError(
            f"BLOCK: JSON output must be an object, got {type(parsed).__name__}"
        )

    title, code, kind = apply_alias(
        parsed.get("account_title", ""),
        parsed.get("account_code", ""),
    )

    result = InferenceResult(
        account_title=title,
        account_code=code,
        needs_review=bool(parsed.get("needs_review", False)),
        match_kind=kind,
        confidence=float(parsed.get("confidence", 0.0) or 0.0),
    )
    return check_and_rollback(result)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    def _blocked_runner(_: str, __: Path) -> str:
        raise RuntimeError("BLOCK: production MLX runner is not wired in CLI mode")

    try:
        result = run_inference(args.input, mlx_runner=_blocked_runner)
        payload = {
            "account_title": result.account_title,
            "account_code": result.account_code,
            "needs_review": result.needs_review,
            "match_kind": result.match_kind,
            "rollback_triggered": result.rollback_triggered,
        }
        text = json.dumps(payload, ensure_ascii=False, indent=2)
        if args.output:
            args.output.write_text(text, encoding="utf-8")
        else:
            print(text)
    except RuntimeError as e:
        print(str(e), file=sys.stderr)
        sys.exit(2)


if __name__ == "__main__":
    main()
