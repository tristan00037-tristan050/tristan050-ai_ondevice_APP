#!/usr/bin/env python3
"""LLM inference 격리 워커 — chunk_timeout 시 SIGKILL로 안전한 강제 종료.

butler_sidecar.py에서 asyncio.create_subprocess_exec로 호출된다.
stdout에 JSON 결과를 출력한다.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

# 레포 루트를 sys.path에 추가
_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from butler_pc_core.inference.llm_runtime import LlmRuntime


def _default_model_path() -> str:
    return os.environ.get("BUTLER_MODEL_PATH", "")


def main() -> None:
    p = argparse.ArgumentParser(description="Butler chunk inference worker")
    p.add_argument("--params", required=True, help="JSON-encoded _AnalyzeParams.__dict__")
    p.add_argument("--chunk-idx", type=int, required=True)
    args = p.parse_args()

    params: dict = json.loads(args.params)
    chunk_idx: int = args.chunk_idx

    # 카드 프롬프트 로드
    system_prompt = "당신은 유능한 사무 보조 AI입니다."
    user_tmpl = "{{ query }}"
    try:
        from butler_pc_core.prompts.cards import load_card_prompt
        card = load_card_prompt(params.get("card_mode", "free"))
        system_prompt = card.get("system_prompt", system_prompt)
        user_tmpl = card.get("user_prompt_template", user_tmpl)
    except Exception:
        pass

    # 첨부 파일 텍스트 읽기
    file_texts: list[str] = []
    for fp in params.get("file_paths", []):
        try:
            file_texts.append(Path(fp).read_text(encoding="utf-8", errors="replace"))
        except Exception:
            pass

    query: str = params.get("query", "")
    user_content = user_tmpl.replace("{{ query }}", query)
    if file_texts:
        user_content += "\n\n## 첨부 파일 내용\n" + "\n\n---\n".join(file_texts)

    # Qwen3 ChatML 포맷 — <s>[INST] 형식(LLaMA-2)은 Qwen3에서 빈 응답 유발
    prompt = (
        f"<|im_start|>system\n{system_prompt}<|im_end|>\n"
        f"<|im_start|>user\n{user_content}<|im_end|>\n"
        f"<|im_start|>assistant\n"
    )

    llm = LlmRuntime(model_path=_default_model_path() or None)
    result_text = llm.generate(prompt, max_tokens=1024)

    print(json.dumps({
        "chunk_id": chunk_idx,
        "result": result_text,
        "card_mode": params.get("card_mode", "free"),
    }))


if __name__ == "__main__":
    main()
