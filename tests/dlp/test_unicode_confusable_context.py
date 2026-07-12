import json
from pathlib import Path

from butler_pc_core.connect_loop.scan_normalization import (
    _apply_observed_confusables_contextual,
    _map_observed_digit_confusables,
    load_observed_confusable_mappings,
)


def test_ascii_letters_are_never_globally_mapped():
    text = "ORDER ID OIl office 2026"
    assert _map_observed_digit_confusables(text, {"O": "0", "I": "1", "l": "1"}) == text


def test_observed_non_ascii_confusable_requires_numeric_context():
    mapping = {"𝟬": "0"}
    assert _map_observed_digit_confusables("코드 12𝟬345", mapping) == "코드 120345"
    assert _map_observed_digit_confusables("기호 𝟬", mapping) == "기호 𝟬"


def test_context_word_allows_four_digit_window_only():
    mapping = {"𝟬": "0"}
    assert _map_observed_digit_confusables("계좌 12𝟬4", mapping) == "계좌 1204"
    assert _map_observed_digit_confusables("일정 12𝟬4", mapping) == "일정 12𝟬4"


def _write_allowlist(path: Path, mappings: list[dict[str, object]]) -> None:
    path.write_text(
        json.dumps(
            {
                "schema_version": "butler.dlp.observed_confusables.v1",
                "corpus_digest": "sha256:" + "a" * 64,
                "mappings": mappings,
                "raw_text_logged": False,
                "status": "MEASURED",
            }
        ),
        encoding="utf-8",
    )


def test_valid_observed_confusable_asset_loads_and_applies(tmp_path):
    path = tmp_path / "allowlist.json"
    _write_allowlist(
        path,
        [{"codepoint": "U+039F", "ascii_digit": "0", "categories": ["phone"], "count": 3}],
    )
    load_observed_confusable_mappings.cache_clear()
    mappings = load_observed_confusable_mappings(str(path))
    assert mappings == (("Ο", "0", ("phone",)),)
    assert _apply_observed_confusables_contextual("전화 1234Ο567", mappings) == "전화 12340567"


def test_invalid_json_fails_safe_to_empty_mapping(tmp_path):
    path = tmp_path / "allowlist.json"
    path.write_text("{invalid", encoding="utf-8")
    load_observed_confusable_mappings.cache_clear()
    assert load_observed_confusable_mappings(str(path)) == ()


def test_ascii_oi_l_mapping_is_rejected_to_empty(tmp_path):
    path = tmp_path / "allowlist.json"
    _write_allowlist(
        path,
        [{"codepoint": "U+004F", "ascii_digit": "0", "categories": ["phone"], "count": 1}],
    )
    load_observed_confusable_mappings.cache_clear()
    assert load_observed_confusable_mappings(str(path)) == ()


def test_nfkc_absorbed_mapping_is_rejected_to_empty(tmp_path):
    path = tmp_path / "allowlist.json"
    _write_allowlist(
        path,
        [{"codepoint": "U+FF10", "ascii_digit": "0", "categories": ["phone"], "count": 1}],
    )
    load_observed_confusable_mappings.cache_clear()
    assert load_observed_confusable_mappings(str(path)) == ()


def test_committed_pending_asset_is_exact_and_raw_zero():
    asset = Path(__file__).resolve().parents[2] / "butler_pc_core/connect_loop/observed_confusable_codepoints.v1.json"
    data = json.loads(asset.read_text(encoding="utf-8"))
    assert set(data) == {"schema_version", "corpus_digest", "mappings", "raw_text_logged", "status"}
    assert data["corpus_digest"] is None
    assert data["mappings"] == []
    assert data["raw_text_logged"] is False
    assert data["status"] == "GROUP_A_CORPUS_PROBE_PENDING"
