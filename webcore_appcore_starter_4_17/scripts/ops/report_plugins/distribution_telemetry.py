"""
Distribution Telemetry Plugin (meta-only)
- Must match legacy score_distribution_telemetry exactly (parity)
"""
from typing import Any, Dict, List
import os
import importlib.util

def _load_telemetry_module():
    here = os.path.dirname(os.path.abspath(__file__))       # .../report_plugins
    ops_dir = os.path.abspath(os.path.join(here, ".."))     # .../scripts/ops
    path = os.path.join(ops_dir, "score_distribution_telemetry.py")
    spec = importlib.util.spec_from_file_location("score_distribution_telemetry", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("spec load failed for score_distribution_telemetry")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod

def plugin(ctx: Dict[str, Any]) -> Dict[str, Any]:
    k = int(ctx.get("k", 0) or 0)
    all_gaps: List[float] = list(ctx.get("all_gaps") or [])
    all_entropies: List[float] = list(ctx.get("all_entropies") or [])
    all_ginis: List[float] = list(ctx.get("all_ginis") or [])
    all_unique_counts: List[int] = list(ctx.get("all_unique_counts") or [])

    m = _load_telemetry_module()
    percentile = m.percentile
    bucketize_entropy = m.bucketize_entropy
    bucketize_gini = m.bucketize_gini
    bucketize_unique_count = m.bucketize_unique_count

    out = {
        "gap_p25": round(percentile(all_gaps, 0.25), 6) if all_gaps else 0.0,
        "gap_p50": round(percentile(all_gaps, 0.50), 6) if all_gaps else 0.0,
        "gap_p75": round(percentile(all_gaps, 0.75), 6) if all_gaps else 0.0,
        "score_entropy_bucket": bucketize_entropy(percentile(all_entropies, 0.50)) if all_entropies else "VERY_LOW",
        "score_gini_bucket": bucketize_gini(percentile(all_ginis, 0.50)) if all_ginis else "LOW_INEQUALITY",
        "unique_score_count_bucket": bucketize_unique_count(round(percentile(all_unique_counts, 0.50)), k) if all_unique_counts else "LOW_DIVERSITY",
    }
    return {"score_distribution_telemetry": out}
