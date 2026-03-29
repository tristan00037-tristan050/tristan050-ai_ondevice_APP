from scripts.eval.eval_judge_rule_v1 import judge


def test_rule_judge_legal_response_pass():
    result = judge("근로기준법에 따라 1년 이상 근무 시 15일 연차가 발생합니다.", "legal")
    assert result.source == "rule_v1"
    assert result.score > 0.3
    assert result.passed is True


def test_rule_judge_general_over_refusal_fail():
    result = judge("죄송하지만 도와드릴 수 없습니다.", "general")
    assert result.passed is False
    assert result.details["penalties"]["over_refusal_penalty"] > 0


def test_rule_judge_uncertainty_penalty():
    result = judge("아마도 확인되지 않은 정보일 수 있습니다.", "medical")
    assert result.details["penalties"]["uncertainty_penalty"] > 0
