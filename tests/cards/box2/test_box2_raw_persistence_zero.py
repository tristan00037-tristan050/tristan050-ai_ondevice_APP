from butler_pc_core.cards.box2.model_chain import build_model_chain_status, contract_only_rewrite


def test_box2_raw_persistence_zero_in_status():
    assert build_model_chain_status(allow_missing_assets=True).raw_persistence == 0


def test_box2_raw_persistence_zero_in_rewrite_response():
    response = contract_only_rewrite(foreign_doc_text="raw_foreign", our_format_text="raw_format")
    assert response["raw_persistence"] == 0
    assert "raw_foreign" not in str(response)
    assert "raw_format" not in str(response)
