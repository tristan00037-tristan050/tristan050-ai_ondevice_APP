from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Set
import os


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {'1', 'true', 'yes', 'y', 'on'}


def _env_csv_set(name: str) -> Set[str]:
    raw = os.getenv(name, '')
    return {item.strip() for item in raw.split(',') if item.strip()}


def _env_csv_list(name: str, default: List[str]) -> List[str]:
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return list(default)
    return [item.strip() for item in raw.split(',') if item.strip()]


@dataclass(slots=True)
class ServerConfig:
    host: str = '0.0.0.0'
    port: int = 8000
    workers: int = 1
    version: str = '1.0.0'

    api_key_required: bool = True
    valid_api_keys: Set[str] = field(default_factory=set)
    allowed_hosts: List[str] = field(default_factory=lambda: ['*'])
    max_request_body_bytes: int = 1 * 1024 * 1024
    max_messages_per_request: int = 100
    max_tokens_limit: int = 4096
    request_timeout_seconds: int = 300
    max_concurrent_requests: int = 10

    default_model: str = 'butler-small'

    turboq_enabled: bool = True
    turboq_bits: int = 3

    log_requests: bool = True
    log_responses: bool = False

    open_paths: Set[str] = field(default_factory=lambda: {
        '/healthz', '/health/readyz', '/version', '/metrics', '/docs', '/openapi.json', '/redoc'
    })


def load_config() -> ServerConfig:
    return ServerConfig(
        host=os.getenv('BUTLER_HOST', '0.0.0.0'),
        port=int(os.getenv('BUTLER_PORT', '8000')),
        workers=int(os.getenv('BUTLER_WORKERS', '1')),
        version=os.getenv('BUTLER_SERVER_VERSION', '1.0.0'),
        api_key_required=_env_bool('BUTLER_API_KEY_REQUIRED', True),
        valid_api_keys=_env_csv_set('BUTLER_API_KEYS'),
        allowed_hosts=_env_csv_list('BUTLER_ALLOWED_HOSTS', ['*']),
        max_request_body_bytes=int(os.getenv('BUTLER_MAX_BODY_BYTES', str(1 * 1024 * 1024))),
        max_messages_per_request=int(os.getenv('BUTLER_MAX_MESSAGES', '100')),
        max_tokens_limit=int(os.getenv('BUTLER_MAX_TOKENS', '4096')),
        request_timeout_seconds=int(os.getenv('BUTLER_REQUEST_TIMEOUT_SECONDS', '300')),
        max_concurrent_requests=int(os.getenv('BUTLER_MAX_CONCURRENT_REQUESTS', '10')),
        default_model=os.getenv('BUTLER_DEFAULT_MODEL', 'butler-small'),
        turboq_enabled=_env_bool('BUTLER_TURBOQ_ENABLED', True),
        turboq_bits=int(os.getenv('BUTLER_TURBOQ_BITS', '3')),
        log_requests=_env_bool('BUTLER_LOG_REQUESTS', True),
        log_responses=False,
    )


config = load_config()
