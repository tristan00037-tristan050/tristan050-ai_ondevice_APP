from scripts.eval.eval_domain_v3 import DOMAIN_EVAL_SETS, run_domain_eval


class KeywordModel:
    def generate_text(self, prompt: str, max_new_tokens: int = 256, timeout_sec: float = 10.0):
        for scenarios in DOMAIN_EVAL_SETS.values():
            for scenario in scenarios:
                if scenario["prompt"] == prompt:
                    return " ".join(scenario["keywords"])
        return "응답"


def test_domain_scenarios_count():
    assert all(len(v) >= 10 for v in DOMAIN_EVAL_SETS.values())


def test_domain_dry_run_pass():
    result = run_domain_eval(None, None, dry_run=True)
    assert result.all_passed is True
    assert result.passed["legal"] is True


def test_domain_dry_run_has_rule_judge_fields():
    result = run_domain_eval(None, None, dry_run=True)
    row = result.scenario_results["legal"][0]
    assert {"judge_score", "judge_source", "judge_confidence", "final_score"}.issubset(row.keys())
    assert row["judge_source"] == "rule_v1"
    assert row["judge_score"] is not None


def test_domain_real_pass_keyword_model():
    result = run_domain_eval(KeywordModel(), None, dry_run=False)
    assert result.all_passed is True
    assert result.scores["finance"] >= 0.7
