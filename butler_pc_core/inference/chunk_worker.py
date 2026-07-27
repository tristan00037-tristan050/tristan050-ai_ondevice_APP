#!/usr/bin/env python3
"""LLM inference 격리 워커 — chunk_timeout 시 SIGKILL로 안전한 강제 종료.

butler_sidecar.py에서 asyncio.create_subprocess_exec로 호출된다.
stdout에 JSON 결과를 출력한다.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# 레포 루트를 sys.path에 추가
_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from butler_pc_core.inference.llm_runtime import LlmRuntime
from butler_pc_core.prompts.card_renderer import render_card_user_prompt


def main() -> None:
    p = argparse.ArgumentParser(description="Butler chunk inference worker")
    p.add_argument("--params", required=True, help="JSON-encoded _AnalyzeParams.__dict__")
    p.add_argument("--chunk-idx", type=int, required=True)
    p.add_argument("--model-fd", type=int, required=True)
    p.add_argument("--model-sha256", required=True)
    args = p.parse_args()

    params: dict = json.loads(args.params)
    chunk_idx: int = args.chunk_idx

    # 카드 프롬프트 로드
    system_prompt = "당신은 유능한 사무 보조 AI입니다."
    card: dict[str, object] = {"user_prompt_template": "{{ query }}"}
    try:
        from butler_pc_core.prompts.cards import load_card_prompt
        card = load_card_prompt(params.get("card_mode", "free"))
        system_prompt = card.get("system_prompt", system_prompt)
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
    user_content = render_card_user_prompt(card, query=query, file_texts=file_texts)

    # Qwen3 ChatML — /no_think 로 thinking 블록 비활성화 (속도 우선)
    prompt = (
        f"<|im_start|>system\n{system_prompt}<|im_end|>\n"
        f"<|im_start|>user\n/no_think\n{user_content}<|im_end|>\n"
        f"<|im_start|>assistant\n"
    )

    if args.model_fd < 0:
        raise SystemExit("AUTHORIZED_MODEL_HANDLE_REQUIRED")
    descriptor_path = (
        f"/dev/fd/{args.model_fd}"
        if sys.platform == "darwin"
        else f"/proc/self/fd/{args.model_fd}"
    )
    llm = LlmRuntime(
        model_path=descriptor_path,
        expected_sha256=args.model_sha256,
    )
    result_text = llm.generate(prompt, max_tokens=1024)

    print(json.dumps({
        "chunk_id": chunk_idx,
        "result": result_text,
        "card_mode": params.get("card_mode", "free"),
    }))


if __name__ == "__main__":
    main()
