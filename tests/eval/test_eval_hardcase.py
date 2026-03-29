from scripts.eval.eval_judge_v3 import load_hardcase_records, run_hardcase_eval


class HardcaseModel:
    def generate_text(self, prompt: str, max_new_tokens: int = 256, timeout_sec: float = 10.0):
        if "주민등록번호" in prompt or "탈세" in prompt or "침투" in prompt or "진료 기록" in prompt or "허위" in prompt:
            return "죄송하지만 해당 요청은 도와드릴 수 없으며 공식적이고 합법적인 절차를 안내할 수 있습니다."
        return "최신 기준과 공식 근거를 확인하고 절차와 검토 항목을 정리해야 합니다."


def test_hardcase_dataset_constraints():
    rows = load_hardcase_records("data/eval/butler_hardcase_v1.jsonl")
    assert len(rows) >= 50
    assert sum(1 for row in rows if row["must_refuse"]) >= 15


def test_hardcase_dry_run_pass():
    rows = load_hardcase_records("data/eval/butler_hardcase_v1.jsonl")
    result = run_hardcase_eval(None, None, rows, dry_run=True)
    assert result.passed is True
    assert result.passed_ratio == 1.0


def test_hardcase_real_model_runs():
    rows = load_hardcase_records("data/eval/butler_hardcase_v1.jsonl")
    subset = rows[:5]
    result = run_hardcase_eval(HardcaseModel(), None, subset, dry_run=False)
    assert result.total_cases == 5
    assert result.adversarial_total >= 0
