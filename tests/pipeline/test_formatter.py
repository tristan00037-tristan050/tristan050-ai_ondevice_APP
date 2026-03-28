from scripts.pipeline.formatter_v2 import DataFormatter


class DummyTokenizer:
    def apply_chat_template(self, messages, tokenize=False, add_generation_prompt=True, enable_thinking=False):
        assert enable_thinking is False
        return "ok"


def test_format_document_creates_digest():
    formatter = DataFormatter()
    text = "첫 줄\n둘째 줄\n셋째 줄\n넷째 줄"
    record = formatter.format_document(text, "general", 0.8, "source.txt")
    assert record is not None
    assert len(record.output_digest_sha256) == 16
    assert "다음 내용을 읽고 이어지는 내용을 작성하세요" in record.prompt


def test_validate_template_dummy_tokenizer():
    formatter = DataFormatter()
    assert formatter.validate_template(DummyTokenizer()) is True


def test_format_qa():
    formatter = DataFormatter()
    record = formatter.format_qa("질문", "답변", "legal", 0.9, "qa")
    assert record.prompt == "질문"
    assert record.completion == "답변"
