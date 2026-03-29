from __future__ import annotations

import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Union


REGRESSION_THRESHOLD = -0.05
BASELINE_PATH = "data/eval/baseline_scores_v3.json"

METRIC_DIRECTIONS = {
    "bleu4": "higher",
    "rouge_l": "higher",
    "avg_latency_sec": "lower",
    "policy_refusal_accuracy": "higher",
    "hallucination_ratio": "lower",
    "domain_legal": "higher",
    "domain_finance": "higher",
    "domain_medical": "higher",
    "domain_admin": "higher",
    "domain_general": "higher",
    "hardcase_pass_ratio": "higher",
    "hardcase_refusal_ratio": "higher",
}


@dataclass
class RegressionResult:
    baseline_exists: bool
    comparisons: Dict[str, dict]
    regressions: List[str]
    passed: bool
    fail_reasons: List[str]
    baseline_action: str


def _load_baseline_file(path: Path) -> Optional[dict]:
    if not path.exists():
        return None
    data = json.loads(path.read_text(encoding="utf-8"))
    if "scores" in data and isinstance(data["scores"], dict):
        return data
    return {"scores": data, "updated_at": None, "model_version": None, "source_report": None}


def _change_ratio(metric: str, current: float, baseline: float) -> Optional[float]:
    if baseline is None:
        return None
    direction = METRIC_DIRECTIONS.get(metric, "higher")
    if baseline == 0:
        # zero-baseline: use absolute delta to avoid division by zero
        delta = float(current) - float(baseline)
        return delta if direction == "higher" else -delta
    if direction == "higher":
        return (float(current) - float(baseline)) / float(baseline)
    return (float(baseline) - float(current)) / float(baseline)


def run_regression_eval(
    current_scores: dict,
    *,
    baseline_path: Union[str, Path] = BASELINE_PATH,
    dry_run: bool = False,
) -> RegressionResult:
    baseline_path = Path(baseline_path)

    if dry_run:
        return RegressionResult(
            baseline_exists=baseline_path.exists(),
            comparisons={},
            regressions=[],
            passed=True,
            fail_reasons=[],
            baseline_action="dry_run_no_write",
        )

    baseline_blob = _load_baseline_file(baseline_path)
    if baseline_blob is None:
        return RegressionResult(
            baseline_exists=False,
            comparisons={},
            regressions=[],
            passed=True,
            fail_reasons=[],
            baseline_action="create_pending_on_pass",
        )

    baseline_scores = baseline_blob.get("scores", {})
    comparisons: Dict[str, dict] = {}
    regressions: List[str] = []
    fail_reasons: List[str] = []

    for metric, current in current_scores.items():
        baseline = baseline_scores.get(metric)
        change = _change_ratio(metric, current, baseline)
        if change is None:
            continue
        comparisons[metric] = {
            "baseline": baseline,
            "current": current,
            "change_ratio": change,
            "direction": METRIC_DIRECTIONS.get(metric, "higher"),
        }
        if change < REGRESSION_THRESHOLD:
            regressions.append(metric)
            fail_reasons.append(f"EVAL_FAIL_REGRESSION_{metric.upper()}:{change:.3f}")

    return RegressionResult(
        baseline_exists=True,
        comparisons=comparisons,
        regressions=regressions,
        passed=len(fail_reasons) == 0,
        fail_reasons=fail_reasons,
        baseline_action="update_on_pass",
    )


def persist_baseline(
    scores: dict,
    *,
    baseline_path: Union[str, Path] = BASELINE_PATH,
    model_version: str,
    report_path: str,
) -> None:
    baseline_path = Path(baseline_path)
    baseline_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "scores": scores,
        "updated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "model_version": model_version,
        "source_report": report_path,
    }
    baseline_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
