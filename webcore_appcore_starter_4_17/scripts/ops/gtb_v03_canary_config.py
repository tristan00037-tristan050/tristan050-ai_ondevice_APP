#!/usr/bin/env python3
"""
GTB v0.3 Canary Config Loader (operational knobs)
Config와 Policy 분리: operational knobs는 config, algorithmic constraints는 policy
"""

import json
import os
from typing import Dict, Optional, Tuple


# Config 파일 경로 (환경 변수로 override 가능)
CONFIG_FILE = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
    "config", "step4b", "gtb_v03_canary_config.json"
)

# Config 캐시
_config_cache: Optional[Dict] = None
_config_err_cache: Optional[str] = None


def load_canary_config() -> Tuple[Optional[Dict], Optional[str], str]:
    """
    Canary config 로드 (operational knobs)
    
    Returns:
        (config_obj | None, err_code | None, config_source)
        - config_obj: 로드 성공 시 딕셔너리
        - err_code: 오류 시 reason_code
        - config_source: "FILE", "ENV", "MISSING_FAILCLOSED"
    """
    global _config_cache, _config_err_cache
    
    # 캐시 확인
    if _config_cache is not None:
        return _config_cache, None, "FILE"
    
    if _config_err_cache is not None:
        return None, _config_err_cache, "MISSING_FAILCLOSED"
    
    # 환경 변수 확인 (우선순위)
    env_canary_percent = os.environ.get("GTB_CANARY_PERCENT")
    env_kill_switch = os.environ.get("GTB_CANARY_KILL_SWITCH")
    env_routing_seed = os.environ.get("GTB_CANARY_ROUTING_SEED")
    
    if env_canary_percent is not None or env_kill_switch is not None:
        # 환경 변수에서 로드
        try:
            canary_percent = int(env_canary_percent) if env_canary_percent else 0
            kill_switch = env_kill_switch.lower() == "true" if env_kill_switch else False
            routing_seed = env_routing_seed if env_routing_seed else "default"
            
            # 검증
            if canary_percent < 0 or canary_percent > 100:
                return None, "CANARY_CONFIG_INVALID_FAILCLOSED", "ENV"
            
            config = {
                "canary_percent": canary_percent,
                "kill_switch": kill_switch,
                "routing_seed": routing_seed,
                "_config_source": "ENV",
            }
            _config_cache = config
            return config, None, "ENV"
        except (ValueError, TypeError):
            return None, "CANARY_CONFIG_INVALID_FAILCLOSED", "ENV"
    
    # 파일에서 로드
    if not os.path.exists(CONFIG_FILE):
        _config_err_cache = "CANARY_CONFIG_INVALID_FAILCLOSED"
        return None, "CANARY_CONFIG_INVALID_FAILCLOSED", "MISSING_FAILCLOSED"
    
    if not os.access(CONFIG_FILE, os.R_OK):
        _config_err_cache = "CANARY_CONFIG_INVALID_FAILCLOSED"
        return None, "CANARY_CONFIG_INVALID_FAILCLOSED", "MISSING_FAILCLOSED"
    
    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            config = json.load(f)
    except (json.JSONDecodeError, UnicodeDecodeError, IOError):
        _config_err_cache = "CANARY_CONFIG_INVALID_FAILCLOSED"
        return None, "CANARY_CONFIG_INVALID_FAILCLOSED", "MISSING_FAILCLOSED"
    
    # 스키마 검증
    if not isinstance(config, dict):
        _config_err_cache = "CANARY_CONFIG_INVALID_FAILCLOSED"
        return None, "CANARY_CONFIG_INVALID_FAILCLOSED", "MISSING_FAILCLOSED"
    
    # 필수 필드 확인
    canary_percent = config.get("canary_percent")
    kill_switch = config.get("kill_switch")
    routing_seed = config.get("routing_seed", "default")
    
    if canary_percent is None:
        _config_err_cache = "CANARY_CONFIG_INVALID_FAILCLOSED"
        return None, "CANARY_CONFIG_INVALID_FAILCLOSED", "MISSING_FAILCLOSED"
    
    if kill_switch is None:
        _config_err_cache = "CANARY_CONFIG_INVALID_FAILCLOSED"
        return None, "CANARY_CONFIG_INVALID_FAILCLOSED", "MISSING_FAILCLOSED"
    
    # 타입 및 범위 검증
    if not isinstance(canary_percent, int):
        _config_err_cache = "CANARY_CONFIG_INVALID_FAILCLOSED"
        return None, "CANARY_CONFIG_INVALID_FAILCLOSED", "MISSING_FAILCLOSED"
    
    if canary_percent < 0 or canary_percent > 100:
        _config_err_cache = "CANARY_CONFIG_INVALID_FAILCLOSED"
        return None, "CANARY_CONFIG_INVALID_FAILCLOSED", "MISSING_FAILCLOSED"
    
    if not isinstance(kill_switch, bool):
        _config_err_cache = "CANARY_CONFIG_INVALID_FAILCLOSED"
        return None, "CANARY_CONFIG_INVALID_FAILCLOSED", "MISSING_FAILCLOSED"
    
    if not isinstance(routing_seed, str):
        _config_err_cache = "CANARY_CONFIG_INVALID_FAILCLOSED"
        return None, "CANARY_CONFIG_INVALID_FAILCLOSED", "MISSING_FAILCLOSED"
    
    # 정규화된 config 반환 (config_source 포함)
    normalized_config = {
        "canary_percent": canary_percent,
        "kill_switch": kill_switch,
        "routing_seed": routing_seed,
        "_config_source": "FILE",
    }
    
    _config_cache = normalized_config
    return normalized_config, None, "FILE"

