from butler_pc_core.connect_loop.scan_normalization import _map_observed_digit_confusables


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
