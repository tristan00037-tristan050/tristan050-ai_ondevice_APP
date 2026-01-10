"""
Report Plugin Registry (v1)
- meta-only only
- v1: empty plugins => no behavior change
"""
from typing import Dict, List, Callable, Any
PluginFn = Callable[[Dict[str, Any]], Dict[str, Any]]

def get_plugins() -> List[PluginFn]:
    return []

def run_plugins(ctx: Dict[str, Any]) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    plugin_error_count = 0
    for fn in get_plugins():
        try:
            sec = fn(ctx) or {}
            out.update(sec)
        except Exception:
            plugin_error_count += 1
    if plugin_error_count:
        out["plugin_error_count"] = plugin_error_count
    return out

