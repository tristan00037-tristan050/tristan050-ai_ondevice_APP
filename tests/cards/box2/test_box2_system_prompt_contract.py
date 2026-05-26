from butler_pc_core.cards.box2.model_chain import REQUIRED_OUTPUT_FIELDS, build_rewrite_system_prompt


def test_box2_system_prompt_contract_exact_fields():
    prompt = build_rewrite_system_prompt()
    positions = [prompt.index(field) for field in REQUIRED_OUTPUT_FIELDS]
    assert positions == sorted(positions)


def test_box2_system_prompt_instructs_uncertainty_not_fabrication():
    prompt = build_rewrite_system_prompt()
    assert "확인 필요" in prompt
    assert "inventing facts" in prompt
