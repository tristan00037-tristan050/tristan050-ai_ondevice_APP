"""Butler TurboQuant package.

Research-faithful scaffold for TurboQuant-style KV cache compression.
This bundle is designed for CPU dry-run verification and integration planning.
"""

from .turboq_core_v1 import LloydMaxQuantizer, PolarQuant, QJLCorrector, TurboQuantKVCache
from .turboq_butler_hook_v1 import ButlerTurboQuantHook
from .turboq_server_v1 import TurboQuantServerManager, init_turboq_server, app
from .turboq_mobile_v1 import MobileTurboQuantConfig, MOBILE_CONFIG
from .turboq_benchmark_v1 import (
    BUTLER_BENCHMARK_SCENARIOS,
    run_butler_benchmark_dryrun,
    run_butler_benchmark_gpu,
)

__all__ = [
    'LloydMaxQuantizer',
    'PolarQuant',
    'QJLCorrector',
    'TurboQuantKVCache',
    'ButlerTurboQuantHook',
    'TurboQuantServerManager',
    'init_turboq_server',
    'app',
    'MobileTurboQuantConfig',
    'MOBILE_CONFIG',
    'BUTLER_BENCHMARK_SCENARIOS',
    'run_butler_benchmark_dryrun',
    'run_butler_benchmark_gpu',
]
