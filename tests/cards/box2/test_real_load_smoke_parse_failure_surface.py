"""Codex P1 regression guard (2026-05-26, PR #755).

Fabricating ``{field: "확인 필요"}`` on parse failure scored 1.0 across all five
evaluator metrics, allowing the run to claim PASS_V2_FULL_METRIC without ever
producing a parseable rewrite. parse failure must surface as None so the
evaluator's ``_output_mapping`` coerces it to ``{}`` and every score fails.
"""
from __future__ import annotations

from unittest.mock import patch

from butler_pc_core.cards.box2 import real_load_smoke
from butler_pc_core.cards.box2.evaluator import (
    _call_model_chain,
    format_match_score,
    required_field_coverage,
    rewrite_structure_accuracy,
    semantic_preservation_score,
    unsupported_fact_rate,
)
from butler_pc_core.cards.box2.real_load_smoke import (
    REQUIRED_OUTPUT_FIELDS,
    LoadedBox2Helper3Chain,
)


def _make_chain(generated_text: str) -> LoadedBox2Helper3Chain:
    chain = LoadedBox2Helper3Chain(model=object(), tokenizer=object(), multi_lora_strategy="set_adapter_list")
    chain.generate_text = lambda text, *, max_new_tokens=256: generated_text  # type: ignore[method-assign]
    return chain


def test_unparseable_output_does_not_fabricate_perfect_score():
    chain = _make_chain("<unparseable garbage with no labeled fields>")
    result = chain.generate_case({"case_id": "C0"})
    assert result is None, (
        f"parse failure must surface as None instead of fabricating fallback: {result!r}"
    )
    if result is not None:  # defensive — see above
        assert "확인 필요" not in result.values(), "fabricated '확인 필요' fallback resurfaced"


def test_parseable_output_passes_through():
    labeled = "\n".join(f"{field}: value-{i}" for i, field in enumerate(REQUIRED_OUTPUT_FIELDS))
    chain = _make_chain(labeled)
    result = chain.generate_case({"case_id": "C1"})
    assert result is not None
    assert list(result.keys()) == list(REQUIRED_OUTPUT_FIELDS)
    assert result[REQUIRED_OUTPUT_FIELDS[0]] == "value-0"


def test_parse_failure_via_evaluator_fails_all_metric_gates():
    """End-to-end: evaluator coerces None to {} so the five gates fail honestly."""
    chain = _make_chain("<unparseable>")
    output = _call_model_chain(chain, {"case_id": "C2"})
    assert output == {}, f"expected empty dict from None, got {output!r}"

    structure = rewrite_structure_accuracy(output)
    coverage = required_field_coverage(output, list(REQUIRED_OUTPUT_FIELDS))
    fact_rate = unsupported_fact_rate(output, [])
    fmt = format_match_score(output, list(REQUIRED_OUTPUT_FIELDS))
    semantic = semantic_preservation_score(output, [])

    assert structure < 0.85, structure
    assert coverage < 0.90, coverage
    assert fmt < 0.85, fmt
    assert semantic < 0.85, semantic
    # fact_rate stays at 0.0 because there are no facts to fabricate, but the
    # other four gates already block PASS_V2_FULL_METRIC. Document the value
    # for completeness so a regression to non-zero would still surface here.
    assert 0.0 <= fact_rate <= 0.03


def test_generate_case_uses_parse_labeled_output():
    """Guard against accidental re-introduction of fabrication via patch."""
    chain = _make_chain("anything")
    with patch.object(real_load_smoke, "parse_labeled_output", return_value=None) as mocked:
        result = chain.generate_case({"case_id": "C3"})
    mocked.assert_called_once()
    assert result is None
