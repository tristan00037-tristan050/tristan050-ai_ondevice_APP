from scripts.pipeline.quality_filter_v2 import QualityFilter


def test_quality_filter_general_pass():
    qf = QualityFilter()
    text = "대한민국 헌법은 국민의 기본권을 보장합니다. 법률은 평등하게 적용되어야 합니다. 누구도 차별받지 않습니다."
    result = qf.evaluate(text)
    assert result.passed
    assert result.score >= 0.3


def test_quality_filter_restricted_domain_rejects_hallucination():
    qf = QualityFilter()
    text = "이 판결은 법적으로 추정되며 판결이 내려진 것으로 보인다. 법원과 계약서 조항을 확인해야 한다."
    result = qf.evaluate(text)
    assert not result.passed
    assert result.reject_reason == "hallucination_dense"


def test_quality_filter_rejects_ngram_duplication():
    qf = QualityFilter()
    repeated = "반복 문장 테스트 " * 40
    result = qf.evaluate(repeated)
    assert not result.passed
    assert result.reject_reason in {"ngram_dup_too_high", "score_too_low"}
