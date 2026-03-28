from __future__ import annotations

from typing import Any

from fastapi import FastAPI, HTTPException

from .turboq_butler_hook_v1 import ButlerTurboQuantHook


class TurboQuantServerManager:
    def __init__(self, model: Any | None, bits: int = 3, enabled: bool = True, qjl_n_bits: int = 2048):
        self.model = model
        self.enabled = bool(enabled)
        self.incompatible_request_count = 0
        self.hook: ButlerTurboQuantHook | None = None
        if self.enabled and self.model is not None:
            self.hook = ButlerTurboQuantHook(bits=bits, mode='wrapper', qjl_n_bits=qjl_n_bits)
            self.hook.apply_to_model(model)

    def get_status(self) -> dict[str, Any]:
        if not self.enabled or self.hook is None:
            return {'turboq_enabled': False}
        stats = self.hook.get_memory_stats()
        return {
            'turboq_enabled': True,
            'bits': stats['bits_after'],
            'compression_ratio_target': stats['compression_ratio_target'],
            'fallback_count': stats['fallback_count'],
            'incompatible_request_count': stats['incompatible_request_count'],
            'measured_compression_ratio': stats['measured_compression_ratio'],
            'measured_memory_reduction': stats['measured_memory_reduction'],
        }


app = FastAPI(title='Butler AI Server')
turboq_manager: TurboQuantServerManager | None = None


def init_turboq_server(model: Any | None, bits: int = 3, enabled: bool = True, qjl_n_bits: int = 2048) -> TurboQuantServerManager:
    global turboq_manager
    turboq_manager = TurboQuantServerManager(model=model, bits=bits, enabled=enabled, qjl_n_bits=qjl_n_bits)
    return turboq_manager


@app.get('/v1/turboq/status')
async def turboq_status() -> dict[str, Any]:
    if turboq_manager is None:
        return {'turboq_enabled': False}
    return turboq_manager.get_status()


@app.post('/v1/chat/completions')
async def chat_completions(request: dict[str, Any]) -> dict[str, Any]:
    # Contract is intentionally unchanged. TurboQuant is treated as an internal
    # hook and this placeholder does not claim serving completeness.
    raise HTTPException(status_code=501, detail='serving handler must be wired by main development team')
