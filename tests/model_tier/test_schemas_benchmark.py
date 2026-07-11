from __future__ import annotations

import json
import os
import subprocess
import sys
from dataclasses import asdict
from pathlib import Path

import jsonschema

from butler_pc_core.model_tier.benchmark_contracts import BenchmarkSample, summarize_benchmark
from butler_pc_core.model_tier.capability_registry import phase0_default_registry
from butler_pc_core.model_tier.device_profiler import collect_device_profile
from butler_pc_core.model_tier.task_profiler import classify_task_complexity


ROOT = Path(__file__).resolve().parents[2]
SCHEMAS = ROOT / "schemas" / "model_tier"


def _schema(name: str) -> dict:
    return json.loads((SCHEMAS / name).read_text(encoding="utf-8"))


def test_all_six_required_schemas_are_draft_2020_12() -> None:
    names = {
        "model_variant_v1.schema.json",
        "device_profile_v1.schema.json",
        "task_profile_v1.schema.json",
        "tier_decision_v1.schema.json",
        "model_tier_shadow_record_v1.schema.json",
        "benchmark_result_v1.schema.json",
    }
    assert {path.name for path in SCHEMAS.glob("*.json")} == names
    for name in names:
        schema = _schema(name)
        assert schema["$schema"] == "https://json-schema.org/draft/2020-12/schema"
        jsonschema.Draft202012Validator.check_schema(schema)


def test_registry_device_and_task_payloads_validate_against_schemas() -> None:
    variant = next(iter(phase0_default_registry().variants.values())).persistable_dict()
    profile = collect_device_profile(
        {
            "total_memory_bytes": 32 * 1024**3,
            "available_memory_bytes": 12 * 1024**3,
            "chip_family": "Apple M4",
        }
    ).persistable_dict()
    task = classify_task_complexity(
        "1",
        {
            "input_chars": 100,
            "attachment_count": 0,
            "total_attachment_bytes": 0,
            "requested_output_tokens": 0,
            "reference_count": 0,
            "structured_output_required": False,
            "deterministic_path_available": True,
            "ambiguity_score": 0.1,
        },
    ).persistable_dict()
    jsonschema.validate(variant, _schema("model_variant_v1.schema.json"))
    jsonschema.validate(profile, _schema("device_profile_v1.schema.json"))
    jsonschema.validate(task, _schema("task_profile_v1.schema.json"))


def _sample(
    run_kind: str,
    iteration: int,
    *,
    fixture_id: str,
    complexity_bucket: str,
) -> BenchmarkSample:
    digest = "sha256:" + "1" * 64
    return BenchmarkSample(
        schema_version="butler.model_tier_benchmark_sample.v1",
        box_id="3",
        complexity_bucket=complexity_bucket,
        fixture_id=fixture_id,
        input_digest=digest,
        device_id_digest=digest,
        build_sha="a" * 40,
        model_digest=digest,
        variant_id="box3_v9_2_r2b_1p7_q4_k_m",
        run_kind=run_kind,  # type: ignore[arg-type]
        iteration=iteration,
        load_ms=float(iteration + 1),
        ttft_ms=float(iteration + 2),
        total_latency_ms=float(iteration + 3),
        tokens_in=100,
        tokens_out=200,
        tokens_per_second=10.0,
        rss_before_bytes=100,
        rss_peak_bytes=150,
        rss_after_bytes=120,
        available_memory_before_bytes=1000,
        available_memory_after_bytes=900,
        thermal_before="NOMINAL",
        thermal_after="FAIR",
        low_power_mode=False,
        battery_delta_percent=0.1,
        quality_gate_pass=True,
        schema_pass=True,
        dlp_pass=True,
        grounding_pass=True,
        escalation_recommended=False,
        device_profile_valid=True,
        failed=False,
    )


def test_benchmark_requires_cold_three_warm_ten_and_emits_p50_p95() -> None:
    buckets = ("short", "medium", "long_multi_evidence")
    rows = [
        _sample(
            "cold",
            index,
            fixture_id=f"fixture-{index:02d}",
            complexity_bucket="short",
        )
        for index in range(3)
    ]
    for fixture_index in range(30):
        for warm_index in range(10):
            rows.append(
                _sample(
                    "warm",
                    fixture_index * 10 + warm_index + 3,
                    fixture_id=f"fixture-{fixture_index:02d}",
                    complexity_bucket=buckets[fixture_index // 10],
                )
            )
    result = summarize_benchmark(rows)
    assert result["protocol_complete"] is True
    assert result["cold_count"] == 3
    assert result["warm_count"] == 300
    assert result["fixture_count"] == 30
    assert result["metrics"]["total_latency_ms_p95"] >= result["metrics"]["total_latency_ms_p50"]
    jsonschema.validate(result, _schema("benchmark_result_v1.schema.json"))


def test_benchmark_cli_runs_from_repo_root_without_pythonpath(tmp_path: Path) -> None:
    sample_path = tmp_path / "samples.jsonl"
    sample_path.write_text(
        json.dumps(
            asdict(
                _sample(
                    "warm",
                    0,
                    fixture_id="fixture-00",
                    complexity_bucket="short",
                )
            ),
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    env = dict(os.environ)
    env.pop("PYTHONPATH", None)
    completed = subprocess.run(
        [sys.executable, "scripts/benchmark_model_tier_phase0.py", str(sample_path)],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 2
    assert '"schema_version": "butler.model_tier_benchmark_result.v1"' in completed.stdout
    markers = dict(
        line.split("=", 1)
        for line in completed.stderr.splitlines()
        if "=" in line
    )
    assert markers.get("MODEL_TIER_BENCHMARK_OK") == "1"
    assert "ModuleNotFoundError" not in completed.stderr
