from butler_pc_core.cards.box2.model_chain import build_model_chain_status, contract_only_rewrite


def test_box2_external_send_zero_in_status():
    assert build_model_chain_status(allow_missing_assets=True).external_send == 0


def test_box2_external_send_zero_in_rewrite_response():
    response = contract_only_rewrite(foreign_doc_text="A", our_format_text="B")
    assert response["external_send"] == 0
