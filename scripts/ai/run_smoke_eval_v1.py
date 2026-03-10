#!/usr/bin/env python3
from __future__ import annotations

import hashlib
from dataclasses import dataclass


@dataclass
class SmokeCase:
    smoke_type: str
    prompt: str


SMOKE_CASES = [
    SmokeCase("general", "안녕하세요. 오늘 할 일을 3줄로 정리해 주세요."),
    SmokeCase("guided_toolcall", "toolcall smoke placeholder"),
    SmokeCase("schema_validator", "schema smoke placeholder"),
]


def digest_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def run_placeholder_inference(prompt: str) -> str:
    return f"[PLACEHOLDER_RESPONSE]{prompt[:16]}"


def main() -> None:
    for case in SMOKE_CASES:
        prompt_digest = digest_text(case.prompt)
        output = run_placeholder_inference(case.prompt)
        output_digest = digest_text(output)

        if not output:
            raise RuntimeError("SMOKE_EMPTY_OUTPUT")
        if output_digest == prompt_digest:
            raise RuntimeError("SMOKE_ECHO_DETECTED")

        print(
            f"SMOKE_PASS type={case.smoke_type} "
            f"prompt_digest={prompt_digest[:8]} output_len={len(output)}"
        )


if __name__ == "__main__":
    main()
