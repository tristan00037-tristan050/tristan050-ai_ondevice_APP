from __future__ import annotations

import asyncio
import json
import time
from threading import Thread
from typing import AsyncGenerator


STREAM_TIMEOUT_SECONDS = 120


def _to_dict_messages(messages) -> list[dict]:
    normalized = []
    for message in messages:
        if hasattr(message, 'model_dump'):
            normalized.append(message.model_dump())
        elif hasattr(message, 'dict'):
            normalized.append(message.dict())
        else:
            normalized.append(dict(message))
    return normalized


async def stream_generator(model, request, req_id: str) -> AsyncGenerator[str, None]:
    chat_id = f'chatcmpl-{req_id}'
    created = int(time.time())

    def make_chunk(content: str = '', finish_reason: str | None = None) -> str:
        payload = {
            'id': chat_id,
            'object': 'chat.completion.chunk',
            'created': created,
            'model': request.model,
            'choices': [{
                'index': 0,
                'delta': {'content': content} if content else {},
                'finish_reason': finish_reason,
            }],
        }
        return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"

    def make_error_chunk(detail: str) -> str:
        payload = {
            'error': {'message': detail, 'type': 'server_error'},
            'request_id': req_id,
        }
        return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"

    try:
        if not model.state.loaded:
            stub_text = f'[{model.model_id} stub] 스트림 테스트 응답입니다.'
            for character in stub_text:
                yield make_chunk(character)
                await asyncio.sleep(0)
            yield make_chunk('', finish_reason='stop')
            yield 'data: [DONE]\n\n'
            return

        from transformers import TextIteratorStreamer

        prompt = model.build_prompt(_to_dict_messages(request.messages))
        tokenized = model.tokenizer(prompt, return_tensors='pt', add_special_tokens=False)
        try:
            import torch
            if torch.cuda.is_available() and hasattr(tokenized, 'to'):
                tokenized = tokenized.to('cuda')
        except Exception:
            pass

        streamer = TextIteratorStreamer(
            model.tokenizer,
            skip_prompt=True,
            skip_special_tokens=True,
            timeout=1.0,
        )
        gen_kwargs = {
            **tokenized,
            'max_new_tokens': request.max_tokens,
            'streamer': streamer,
            'do_sample': request.temperature > 0,
        }
        if request.temperature > 0:
            gen_kwargs['temperature'] = request.temperature
        if model.is_qwen3:
            gen_kwargs['enable_thinking'] = False

        worker = Thread(target=model.model.generate, kwargs=gen_kwargs, daemon=True)
        worker.start()
        deadline = time.monotonic() + STREAM_TIMEOUT_SECONDS
        timed_out = False

        while True:
            if time.monotonic() > deadline:
                timed_out = True
                break
            try:
                token_text = next(streamer)
            except StopIteration:
                break
            except Exception:
                await asyncio.sleep(0)
                if not worker.is_alive():
                    break
                continue
            if token_text:
                yield make_chunk(token_text)
            await asyncio.sleep(0)

        worker.join(timeout=2)
        finish_reason = 'length' if timed_out else 'stop'
        yield make_chunk('', finish_reason=finish_reason)
        yield 'data: [DONE]\n\n'
    except Exception:
        yield make_error_chunk('stream_error')
        yield 'data: [DONE]\n\n'
