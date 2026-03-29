from scripts.eval.eval_safety_v3 import run_safety_eval, POLICY_SENSITIVE_PROMPTS


class SafeModel:
    def generate_text(self, prompt: str, max_new_tokens: int = 256, timeout_sec: float = 10.0):
        if any(row["prompt"] == prompt for row in POLICY_SENSITIVE_PROMPTS):
            return "죄송하지만 해당 요청은 도와드릴 수 없습니다."
        return "확정된 사실과 근거만 안내합니다."


class UnsafeModel:
    def generate_text(self, prompt: str, max_new_tokens: int = 256, timeout_sec: float = 10.0):
        return "아마도 확인되지 않은 정보일 수 있습니다."


def test_safety_dry_run_pass():
    result = run_safety_eval(None, None, [], dry_run=True)
    assert result.passed is True


def test_safety_safe_model_pass():
    records = [{"prompt": "일반 질문", "completion": "참고"}]
    result = run_safety_eval(SafeModel(), None, records, dry_run=False)
    assert result.passed is True
    assert result.policy_refusal_accuracy >= 0.95


def test_safety_unsafe_model_fail():
    records = [{"prompt": "일반 질문", "completion": "참고"} for _ in range(3)]
    result = run_safety_eval(UnsafeModel(), None, records, dry_run=False)
    assert result.passed is False
    assert any(reason.startswith("EVAL_FAIL_HALLUCINATION") or reason.startswith("EVAL_FAIL_POLICY") for reason in result.fail_reasons)
