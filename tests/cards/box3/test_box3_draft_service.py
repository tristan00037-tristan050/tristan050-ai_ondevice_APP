from __future__ import annotations

from butler_pc_core.cards.box3.draft_service import (
    CONTRACT_ONLY_DRAFT,
    MIN_REPETITION_PENALTY,
    MODEL_CHAIN,
    REQUIRED_NO_REPEAT_NGRAM_SIZE,
    SEALED_SHA,
    build_draft_inference_config,
    draft_from_existing,
)


def test_inference_config_enforces_box3_standard():
    config = build_draft_inference_config()
    assert config["repetition_penalty"] == MIN_REPETITION_PENALTY
    assert config["repetition_penalty"] >= 1.2
    assert config["no_repeat_ngram_size"] == REQUIRED_NO_REPEAT_NGRAM_SIZE == 3
    assert config["do_sample"] is False
    assert config["max_new_tokens"] == 300


def test_inference_config_bounds_max_new_tokens():
    assert build_draft_inference_config(99999)["max_new_tokens"] == 1024
    assert build_draft_inference_config(0)["max_new_tokens"] == 1
    assert build_draft_inference_config(150)["max_new_tokens"] == 150


def test_contract_only_when_no_runner():
    result = draft_from_existing("기존 문서 본문", "다음 문서를 요약하세요\n\n{input}")
    assert result.contract_only is True
    assert result.draft_text == CONTRACT_ONLY_DRAFT
    assert result.duration_ms == 0
    assert result.model_chain == MODEL_CHAIN
    assert result.external_send_zero is True
    assert result.raw_saved_zero is True
    assert result.inference_config["repetition_penalty"] >= 1.2


def test_runner_receives_enforced_config_and_filled_prompt():
    captured = {}

    def fake_runner(prompt, config):
        captured["prompt"] = prompt
        captured["config"] = config
        return "생성된 초안"

    result = draft_from_existing(
        "2025년 1분기 매출 50억원",
        "다음 보고서를 요약하세요\n\n{input}",
        runner=fake_runner,
    )
    assert result.contract_only is False
    assert result.draft_text == "생성된 초안"
    assert "2025년 1분기 매출 50억원" in captured["prompt"]
    assert captured["config"]["repetition_penalty"] >= 1.2
    assert captured["config"]["no_repeat_ngram_size"] == 3


def test_prompt_template_without_placeholder_appends_input():
    captured = {}

    def fake_runner(prompt, config):
        captured["prompt"] = prompt
        return "ok"

    draft_from_existing("본문내용", "요약하세요", runner=fake_runner)
    assert "요약하세요" in captured["prompt"]
    assert "본문내용" in captured["prompt"]


def test_sealed_sha_constants_present():
    assert SEALED_SHA["box3_smoke"] == "4d86414ddf74b048d6db011659e4227641257ad0d931faab690dcddeea58cf74"
    assert SEALED_SHA["tool_call"] == "ad852bbb79aee63cc68750eac3ebe02de372d4eb9529659ae065490c78c933ca"
    assert SEALED_SHA["butler_v3"] == "7b4d474cba6cf8113b1402a44a490f153e3beea031ba54827c2fae848b7b4b41"
