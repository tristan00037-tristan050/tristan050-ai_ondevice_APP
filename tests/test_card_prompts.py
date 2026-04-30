"""test_card_prompts.py — 카드 프롬프트 YAML 5요소 검증."""
from __future__ import annotations

import yaml
import pytest
from pathlib import Path

CARDS_DIR = Path(__file__).parent.parent / "butler_pc_core" / "prompts" / "cards"
CARD_FILES = sorted(CARDS_DIR.glob("card_0*.yaml"))

REQUIRED_TOP_KEYS = {"card_id", "input_schema", "output_schema", "system_prompt", "user_prompt_template"}
MIN_FORBIDDEN = 5
MIN_EXAMPLES = 2


def _load(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


@pytest.mark.parametrize("card_path", CARD_FILES, ids=[p.stem for p in CARD_FILES])
def test_card_has_required_top_level_keys(card_path: Path):
    data = _load(card_path)
    missing = REQUIRED_TOP_KEYS - set(data.keys())
    assert not missing, f"{card_path.name}: 필수 키 누락 — {missing}"


@pytest.mark.parametrize("card_path", CARD_FILES, ids=[p.stem for p in CARD_FILES])
def test_card_has_forbidden_actions(card_path: Path):
    data = _load(card_path)
    assert "forbidden_actions" in data, f"{card_path.name}: forbidden_actions 누락"
    actions = data["forbidden_actions"]
    assert isinstance(actions, list), f"{card_path.name}: forbidden_actions 가 list 가 아님"
    assert len(actions) >= MIN_FORBIDDEN, (
        f"{card_path.name}: forbidden_actions {len(actions)}개 — 최소 {MIN_FORBIDDEN}개 필요"
    )


@pytest.mark.parametrize("card_path", CARD_FILES, ids=[p.stem for p in CARD_FILES])
def test_card_has_examples(card_path: Path):
    data = _load(card_path)
    assert "examples" in data, f"{card_path.name}: examples 누락"
    examples = data["examples"]
    assert isinstance(examples, list), f"{card_path.name}: examples 가 list 가 아님"
    assert len(examples) >= MIN_EXAMPLES, (
        f"{card_path.name}: examples {len(examples)}개 — 최소 {MIN_EXAMPLES}개(best+edge) 필요"
    )


@pytest.mark.parametrize("card_path", CARD_FILES, ids=[p.stem for p in CARD_FILES])
def test_card_examples_have_input_and_expected_output(card_path: Path):
    data = _load(card_path)
    examples = data.get("examples", [])
    for i, ex in enumerate(examples):
        assert "input" in ex, f"{card_path.name} examples[{i}]: input 키 누락"
        assert "expected_output" in ex, f"{card_path.name} examples[{i}]: expected_output 키 누락"


@pytest.mark.parametrize("card_path", CARD_FILES, ids=[p.stem for p in CARD_FILES])
def test_card_examples_have_best_and_edge_labels(card_path: Path):
    data = _load(card_path)
    examples = data.get("examples", [])
    labels = {ex.get("label") for ex in examples}
    assert "best" in labels, f"{card_path.name}: examples 에 label=best 없음"
    assert "edge" in labels, f"{card_path.name}: examples 에 label=edge 없음"
