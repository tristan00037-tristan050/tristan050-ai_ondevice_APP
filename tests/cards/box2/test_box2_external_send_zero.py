from pathlib import Path
from butler_pc_core.cards.box2.model_chain import build_model_chain_status, contract_only_rewrite

def test_box2_external_send_zero_in_status():
    assert build_model_chain_status(allow_missing_assets=True).external_send == 0

def test_box2_external_send_zero_in_rewrite_response():
    response = contract_only_rewrite(foreign_doc_text="A", our_format_text="B")
    assert response["external_send"] == 0

def test_box2_code_has_no_external_send_import_patterns():
    root = Path(__file__).resolve().parents[3]
    offenders = []
    for path in (root / "butler_pc_core/cards/box2").rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        for pattern in ("requests.", "httpx.", "aiohttp.", "urllib", "fetch(", "axios"):
            if pattern in text and "localhost" not in text and "127.0.0.1" not in text:
                offenders.append(f"{path.relative_to(root)}:{pattern}")
    assert offenders == []
