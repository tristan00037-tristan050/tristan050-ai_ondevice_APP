from __future__ import annotations

import builtins
from pathlib import Path

import pytest

from butler_pc_core.prompts.card_renderer import render_card_user_prompt
from butler_pc_core.prompts.cards import load_card_prompt


pytestmark = pytest.mark.no_sidecar_token

REPO_ROOT = Path(__file__).resolve().parents[2]


def assert_no_jinja_literals(rendered: str) -> None:
    assert "{{" not in rendered
    assert "{%" not in rendered
    assert "%}" not in rendered


def test_card_mode_4_loads_card_04() -> None:
    card = load_card_prompt("4")

    assert card["card_id"] == "card_04_document_review"


def test_card_04_renders_draft_and_reference_docs_without_jinja_literals() -> None:
    card = load_card_prompt("4")

    rendered = render_card_user_prompt(
        card,
        query="초안 본문입니다.",
        file_texts=["참고 문서 A", "참고 문서 B"],
    )

    assert "초안 본문입니다." in rendered
    assert "## 참고 문서" in rendered
    assert "### 참고 1" in rendered
    assert "참고 문서 A" in rendered
    assert "### 참고 2" in rendered
    assert "참고 문서 B" in rendered
    assert "## 검토 기준" not in rendered
    assert_no_jinja_literals(rendered)


def test_renderer_falls_back_when_jinja_import_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    real_import = builtins.__import__

    def blocked_import(name: str, *args: object, **kwargs: object) -> object:
        if name == "jinja2" or name.startswith("jinja2."):
            raise ImportError("blocked jinja for fallback test")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", blocked_import)

    rendered = render_card_user_prompt(
        load_card_prompt("4"),
        query="폴백 초안",
        file_texts=["폴백 참고"],
    )

    assert "폴백 초안" in rendered
    assert "폴백 참고" in rendered
    assert_no_jinja_literals(rendered)


def test_free_and_legacy_query_template_render_as_before() -> None:
    assert render_card_user_prompt(load_card_prompt("free"), query="일반 질문", file_texts=[]) == "일반 질문"

    rendered = render_card_user_prompt(
        {"user_prompt_template": "요청: {{ query }}"},
        query="기존 템플릿",
        file_texts=["첨부 본문"],
    )

    assert rendered.startswith("요청: 기존 템플릿")
    assert "## 첨부 파일 내용" in rendered
    assert "첨부 본문" in rendered
    assert_no_jinja_literals(rendered)


@pytest.mark.parametrize(
    ("card_mode", "expected_text"),
    [
        ("1", "## 분석 대상 메시지"),
        ("2", "## 외부 문서"),
        ("5", "## 거래내역"),
    ],
)
def test_cards_1_2_5_render_without_jinja_literals(card_mode: str, expected_text: str) -> None:
    rendered = render_card_user_prompt(
        load_card_prompt(card_mode),
        query=f"카드 {card_mode} 입력 본문",
        file_texts=["첨부 자료"],
    )

    assert expected_text in rendered
    assert f"카드 {card_mode} 입력 본문" in rendered
    assert_no_jinja_literals(rendered)


def test_runtime_paths_use_common_renderer_without_direct_query_replace() -> None:
    sidecar = (REPO_ROOT / "butler_sidecar.py").read_text(encoding="utf-8")
    worker = (REPO_ROOT / "butler_pc_core/inference/chunk_worker.py").read_text(encoding="utf-8")

    assert sidecar.count("render_card_user_prompt") >= 3
    assert worker.count("render_card_user_prompt") >= 2
    assert '.replace("{{ query }}"' not in sidecar
    assert '.replace("{{ query }}"' not in worker
