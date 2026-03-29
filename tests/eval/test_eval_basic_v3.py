from scripts.eval.eval_basic_v3 import compute_bleu4, compute_rouge_l, run_basic_eval


class EchoModel:
    def __init__(self, response: str):
        self.response = response

    def generate_text(self, prompt: str, max_new_tokens: int = 256, timeout_sec: float = 10.0):
        return self.response


def test_bleu_identity():
    assert compute_bleu4("버틀러는 기업용 AI입니다", "버틀러는 기업용 AI입니다") >= 0.9


def test_rouge_identity():
    assert compute_rouge_l("버틀러는 기업용 AI입니다", "버틀러는 기업용 AI입니다") >= 0.9


def test_basic_dry_run_pass():
    result = run_basic_eval(None, None, [], dry_run=True)
    assert result.passed is True
    assert result.bleu4 == 0.99


def test_basic_real_pass_with_echo():
    records = [{"prompt": "x", "completion": "정확한 답변", "case_id": "c1"}]
    result = run_basic_eval(EchoModel("정확한 답변"), None, records, dry_run=False)
    assert result.sample_count == 1
    assert result.bleu4 >= 0.9
    assert result.rouge_l >= 0.9


def test_basic_empty_response_fails():
    records = [{"prompt": "x", "completion": "정답", "case_id": "c1"}]
    result = run_basic_eval(EchoModel(""), None, records, dry_run=False)
    assert result.passed is False
    assert any(reason.startswith("EVAL_FAIL_EMPTY_RESPONSE") for reason in result.fail_reasons)
