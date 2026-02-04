"""
Report Plugin Registry (v1)
- meta-only only
- v1: distribution_telemetry plugin only
"""
from typing import Dict, List, Callable, Any
import os
import importlib.util

PluginFn = Callable[[Dict[str, Any]], Dict[str, Any]]

def get_plugins() -> List[PluginFn]:
    """
    Load distribution_telemetry plugin (v1: 1 plugin only)
    Returns empty list on load failure (plugin_error_count will track it)
    """
    plugins: List[PluginFn] = []
    try:
        # Load distribution_telemetry plugin
        here = os.path.dirname(os.path.abspath(__file__))  # .../scripts/ops
        plugin_dir = os.path.join(here, "report_plugins")
        plugin_path = os.path.join(plugin_dir, "distribution_telemetry.py")
        
        spec = importlib.util.spec_from_file_location("distribution_telemetry_plugin", plugin_path)
        if spec is None or spec.loader is None:
            return plugins  # Load failure: return empty (will be tracked as error)
        
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        
        if hasattr(mod, "plugin"):
            plugins.append(mod.plugin)
    except Exception:
        # Load failure: return empty (will be tracked as error)
        pass
    
    return plugins

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

