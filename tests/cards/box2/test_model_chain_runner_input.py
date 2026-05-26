"""Regression guard for Codex P1 #2 (PR #754, 2026-05-25).

The real-load path previously invoked runner(prompt) with only the static
system instruction, never including foreign_doc_text or our_format_text.
A real backend therefore could not rewrite the caller's document and would
be reported as PASS_V2_REWRITE_OUTPUT_VALID if it returned schema-shaped
JSON unrelated to the input.
"""

import json

import pytest

from butler_pc_core.cards.box2 import model_chain as mc
from butler_pc_core.cards.box2.model_chain import (
    REQUIRED_OUTPUT_FIELDS,
    build_rewrite_system_prompt,
    compose_rewrite_runner_input,
    contract_only_rewrite,
)


def _valid_rewrite_payload() -> str:
    return json.dumps({field: f"value_{i}" for i, field in enumerate(REQUIRED_OUTPUT_FIELDS)})


@pytest.fixture
def force_real_load(monkeypatch):
    class _Status:
        load_mode = "real_load_ready"
        status = "PASS_V2_REAL_LOAD_READY"
        blocking_reasons: list[str] = []

    monkeypatch.setattr(mc, "build_model_chain_status", lambda allow_missing_assets=True: _Status())


def test_compose_rewrite_runner_input_includes_all_three_parts():
    prompt = build_rewrite_system_prompt()
    composed = compose_rewrite_runner_input(
        system_prompt=prompt,
        foreign_doc_text="FOREIGN_BODY_TEXT_SENTINEL",
        our_format_text="OUR_FORMAT_TEXT_SENTINEL",
    )
    assert prompt in composed
    assert "FOREIGN_BODY_TEXT_SENTINEL" in composed
    assert "OUR_FORMAT_TEXT_SENTINEL" in composed


def test_real_load_runner_receives_foreign_doc_text(force_real_load):
    captured: dict[str, str] = {}

    def runner(text: str) -> str:
        captured["input"] = text
        return _valid_rewrite_payload()

    foreign_marker = "FOREIGN_DOC_MARKER_UNIQUE_SENTINEL_2026"
    result = contract_only_rewrite(
        foreign_doc_text=foreign_marker,
        our_format_text="OUR_FORMAT",
        runner=runner,
    )
    assert result["status"] == "PASS_V2_REWRITE_OUTPUT_VALID"
    assert foreign_marker in captured["input"], (
        "runner did not receive foreign_doc_text — Codex P1 #2 defect re-introduced"
    )


def test_real_load_runner_receives_our_format_text(force_real_load):
    captured: dict[str, str] = {}

    def runner(text: str) -> str:
        captured["input"] = text
        return _valid_rewrite_payload()

    our_marker = "OUR_FORMAT_MARKER_UNIQUE_SENTINEL_2026"
    contract_only_rewrite(
        foreign_doc_text="FOREIGN",
        our_format_text=our_marker,
        runner=runner,
    )
    assert our_marker in captured["input"], (
        "runner did not receive our_format_text — Codex P1 #2 defect re-introduced"
    )


def test_real_load_runner_still_receives_system_prompt(force_real_load):
    """The system instruction must still be included (no regression on prompt)."""
    captured: dict[str, str] = {}

    def runner(text: str) -> str:
        captured["input"] = text
        return _valid_rewrite_payload()

    contract_only_rewrite(
        foreign_doc_text="FOREIGN",
        our_format_text="OUR",
        runner=runner,
    )
    prompt = build_rewrite_system_prompt()
    assert prompt in captured["input"], "system prompt missing from runner input"
