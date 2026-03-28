from __future__ import annotations

import asyncio
import time
from collections import Counter
from typing import Annotated, List, Literal, Optional

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field

from .auth_middleware_v1 import ButlerAuthMiddleware
from .model_pool_v1 import BASE_MODEL_MAP, model_pool
from .server_config_v1 import ServerConfig, load_config
from .stream_handler_v1 import stream_generator


SERVER_STATS = Counter()


class Message(BaseModel):
    role: Literal['system', 'user', 'assistant']
    content: Annotated[str, Field(max_length=32000)]


class ChatCompletionRequest(BaseModel):
    model: Annotated[str, Field(min_length=1)]
    messages: Annotated[List[Message], Field(min_length=1, max_length=100)]
    max_tokens: Annotated[int, Field(ge=1, le=4096)] = 512
    temperature: Annotated[float, Field(ge=0.0, le=2.0)] = 0.7
    stream: bool = False


def create_app(config: Optional[ServerConfig] = None) -> FastAPI:
    server_config = config or load_config()
    app = FastAPI(
        title='Butler AI Server',
        description='온프레미스 버틀러 AI 서빙 서버 — 외부 전송 없음',
        version=server_config.version,
    )
    app.state.config = server_config
    app.state.request_semaphore = asyncio.Semaphore(server_config.max_concurrent_requests)
    app.add_middleware(ButlerAuthMiddleware, config=server_config)

    @app.get('/healthz')
    async def healthz():
        return {'status': 'ok', 'timestamp': int(time.time())}

    @app.get('/health/readyz')
    async def readyz():
        model_pool.probe_all()
        report = model_pool.readiness_report()
        fatal_models = {k: v for k, v in report.items() if v['state'] == 'error'}
        if fatal_models:
            return JSONResponse(
                status_code=503,
                content={
                    'status': 'not_ready',
                    'loaded_models': model_pool.loaded_count(),
                    'stub_models': model_pool.stub_count(),
                    'errors': fatal_models,
                },
            )
        loaded = model_pool.loaded_count()
        if loaded == 0:
            return {
                'status': 'stub',
                'loaded_models': 0,
                'stub_models': model_pool.stub_count() or len(model_pool.model_ids()),
                'message': '모델 미로드 — stub 모드로 동작 중',
                'readiness': report,
            }
        return {
            'status': 'ready',
            'loaded_models': loaded,
            'stub_models': model_pool.stub_count(),
            'readiness': report,
        }

    @app.get('/v1/models')
    async def list_models():
        now = 1_700_000_000
        return {
            'object': 'list',
            'data': [
                {
                    'id': model_id,
                    'object': 'model',
                    'owned_by': 'butler',
                    'created': now,
                    'base_model': BASE_MODEL_MAP[model_id],
                }
                for model_id in model_pool.model_ids()
            ],
        }

    @app.get('/metrics')
    async def metrics():
        return {
            'requests_total': int(SERVER_STATS['requests_total']),
            'stream_requests_total': int(SERVER_STATS['stream_requests_total']),
            'chat_requests_total': int(SERVER_STATS['chat_requests_total']),
            'loaded_models': model_pool.loaded_count(),
            'stub_models': model_pool.stub_count(),
            'fatal_models': model_pool.fatal_count(),
            'turboq_enabled': server_config.turboq_enabled,
            'turboq_bits': server_config.turboq_bits,
        }

    @app.get('/version')
    async def version():
        return {
            'version': server_config.version,
            'loaded_models': model_pool.loaded_count(),
            'stub_models': model_pool.stub_count(),
            'default_model': server_config.default_model,
            'turboq_enabled': server_config.turboq_enabled,
            'turboq_bits': server_config.turboq_bits,
        }

    @app.post('/v1/chat/completions')
    async def chat_completions(request_body: ChatCompletionRequest, request: Request, req_id: str = Depends(get_request_id)):
        SERVER_STATS['requests_total'] += 1
        SERVER_STATS['chat_requests_total'] += 1
        config: ServerConfig = request.app.state.config
        if len(request_body.messages) > config.max_messages_per_request:
            raise HTTPException(status_code=422, detail='too_many_messages')
        if request_body.max_tokens > config.max_tokens_limit:
            raise HTTPException(status_code=422, detail='max_tokens_exceeds_limit')

        model = model_pool.get_model(request_body.model)
        if model is None:
            raise HTTPException(status_code=404, detail=f'모델 {request_body.model}을 찾을 수 없습니다')
        if model.should_fail_closed():
            raise HTTPException(status_code=503, detail=model.state.fatal_error or 'model_not_ready')

        if request_body.stream:
            SERVER_STATS['stream_requests_total'] += 1
            semaphore = request.app.state.request_semaphore

            async def guarded_stream():
                async with semaphore:
                    async for chunk in stream_generator(model, request_body, req_id):
                        yield chunk

            return StreamingResponse(
                guarded_stream(),
                media_type='text/event-stream',
                headers={
                    'X-Request-Id': req_id,
                    'Cache-Control': 'no-cache',
                    'Connection': 'keep-alive',
                },
            )

        start = time.perf_counter()
        message_dicts = [message.model_dump() for message in request_body.messages]
        async with request.app.state.request_semaphore:
            response_text = await run_in_threadpool(
                model.generate,
                message_dicts,
                request_body.max_tokens,
                request_body.temperature,
            )
        latency_ms = int((time.perf_counter() - start) * 1000)
        return {
            'id': f'chatcmpl-{req_id}',
            'object': 'chat.completion',
            'created': int(time.time()),
            'model': request_body.model,
            'choices': [{
                'index': 0,
                'message': {'role': 'assistant', 'content': response_text},
                'finish_reason': 'stop',
            }],
            'usage': {
                'prompt_tokens': -1,
                'completion_tokens': -1,
                'total_tokens': -1,
            },
            'x_request_id': req_id,
            'x_latency_ms': latency_ms,
        }

    return app


def get_request_id(request: Request) -> str:
    return getattr(request.state, 'request_id', 'missing-request-id')


app = create_app()
