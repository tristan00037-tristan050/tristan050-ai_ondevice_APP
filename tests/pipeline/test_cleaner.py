from scripts.pipeline.cleaner_v2 import DataCleaner


def test_cleaner_masks_pii():
    cleaner = DataCleaner(min_korean_ratio=0.3)
    result = cleaner.clean("한국어 본문입니다. 010-1234-5678 test@example.com 123-45-67890 추가 문장.")
    assert result.passed
    assert "[PHONE]" in result.text
    assert "[EMAIL]" in result.text
    assert "[BIZ_NUM]" in result.text


def test_cleaner_rejects_low_korean_ratio():
    cleaner = DataCleaner(min_korean_ratio=0.5)
    result = cleaner.clean("This is mostly English text with only 한글.")
    assert not result.passed
    assert result.reject_reason.startswith("korean_ratio_low:")


def test_cleaner_rejects_length_out_of_range():
    cleaner = DataCleaner(min_korean_ratio=0.1, min_length=50)
    result = cleaner.clean("짧은 문장입니다.")
    assert not result.passed
    assert result.reject_reason.startswith("length_out_of_range:")
