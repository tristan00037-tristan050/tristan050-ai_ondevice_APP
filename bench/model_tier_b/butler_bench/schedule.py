from __future__ import annotations

import hashlib
import hmac
import re
from typing import Any

from .canonical import canonical_sha256
from .errors import ExitCode, FailClass, GateError

_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_FIXTURE_KEYS = {"fixture_id", "task_id", "input_sha256", "reference_sha256"}
_ROW_KEYS = {
    "epoch", "task_id", "fixture_id", "candidate_id", "model_manifest_sha256",
    "runtime_config_sha256", "phase", "repetition", "physical_position", "deterministic_seed",
}


def verify_fixture_manifest(manifest: dict[str, Any]) -> str:
    if set(manifest) != {"schema_version", "fixtures", "fixture_manifest_sha256"}:
        _block("FIXTURE_MANIFEST_KEYS", ExitCode.SCHEMA)
    if manifest["schema_version"] != "butler.model-tier-b.fixture-manifest.v2.8":
        _block("FIXTURE_MANIFEST_VERSION", ExitCode.SCHEMA)
    fixtures = manifest["fixtures"]
    if not isinstance(fixtures, list) or not fixtures:
        _block("FIXTURES_EMPTY", ExitCode.SCHEMA)
    ids: set[str] = set()
    for fixture in fixtures:
        if not isinstance(fixture, dict) or set(fixture) != _FIXTURE_KEYS:
            _block("FIXTURE_KEYS", ExitCode.SCHEMA)
        if not re.fullmatch(r"[A-Za-z0-9_.-]{1,96}", fixture["fixture_id"]) or fixture["fixture_id"] in ids:
            _block("FIXTURE_ID", ExitCode.SCHEMA)
        ids.add(fixture["fixture_id"])
        if not re.fullmatch(r"[A-Za-z0-9_.-]{1,64}", fixture["task_id"]):
            _block("TASK_ID", ExitCode.SCHEMA)
        for key in ("input_sha256", "reference_sha256"):
            if not isinstance(fixture[key], str) or not _SHA256.fullmatch(fixture[key]):
                _block("FIXTURE_DIGEST", ExitCode.SCHEMA)
    declared = manifest["fixture_manifest_sha256"]
    unsigned = {"schema_version": manifest["schema_version"], "fixtures": fixtures}
    if not isinstance(declared, str) or canonical_sha256(unsigned) != declared:
        _block("FIXTURE_MANIFEST_DIGEST", ExitCode.DIGEST)
    return declared


def build_schedule(policy: dict[str, Any], fixture_manifest: dict[str, Any]) -> dict[str, Any]:
    fixture_digest = verify_fixture_manifest(fixture_manifest)
    if policy["fixture_manifest_sha256"] != fixture_digest:
        _block("POLICY_FIXTURE_BINDING", ExitCode.DIGEST)
    candidates = policy["candidates"]
    fixtures = sorted(fixture_manifest["fixtures"], key=lambda item: (item["task_id"], item["fixture_id"]))
    representative = fixtures[0]
    rows: list[dict[str, Any]] = []
    for epoch in range(1, 6):
        for repetition in (1, 2):
            for position, candidate_id in enumerate(("A", "B"), 1):
                rows.append(_row(policy, candidates, epoch, representative, candidate_id, "warmup", repetition, position))
        for fixture in fixtures:
            for repetition, order in ((1, "AB"), (2, "BA")):
                for position, candidate_id in enumerate(order, 1):
                    rows.append(_row(policy, candidates, epoch, fixture, candidate_id, "measured", repetition, position))
    payload = {
        "schema_version": "butler.model-tier-b.schedule.v2.8",
        "fixture_manifest_sha256": fixture_digest,
        "benchmark_policy_sha256": policy["_payload_sha256"],
        "rows": rows,
    }
    payload["schedule_sha256"] = canonical_sha256(payload)
    verify_schedule(payload, policy, fixture_manifest)
    return payload


def verify_schedule(schedule: dict[str, Any], policy: dict[str, Any], fixture_manifest: dict[str, Any]) -> None:
    keys = {"schema_version", "fixture_manifest_sha256", "benchmark_policy_sha256", "rows", "schedule_sha256"}
    if set(schedule) != keys or schedule["schema_version"] != "butler.model-tier-b.schedule.v2.8":
        _block("SCHEDULE_KEYS", ExitCode.SCHEMA)
    declared = schedule["schedule_sha256"]
    unsigned = {key: value for key, value in schedule.items() if key != "schedule_sha256"}
    if not isinstance(declared, str) or canonical_sha256(unsigned) != declared:
        _block("SCHEDULE_DIGEST", ExitCode.DIGEST)
    if schedule["fixture_manifest_sha256"] != verify_fixture_manifest(fixture_manifest):
        _block("SCHEDULE_FIXTURE", ExitCode.DIGEST)
    rows = schedule["rows"]
    if not isinstance(rows, list) or any(not isinstance(row, dict) or set(row) != _ROW_KEYS for row in rows):
        _block("SCHEDULE_ROWS", ExitCode.SCHEMA)
    fixture_count = len(fixture_manifest["fixtures"])
    if len(rows) != 5 * (4 + 4 * fixture_count):
        _block("SCHEDULE_ROW_COUNT")
    measured = [row for row in rows if row["phase"] == "measured"]
    for epoch in range(1, 6):
        warmups = [row for row in rows if row["epoch"] == epoch and row["phase"] == "warmup"]
        if [(row["candidate_id"], row["repetition"], row["physical_position"]) for row in warmups] != [
            ("A", 1, 1), ("B", 1, 2), ("A", 2, 1), ("B", 2, 2)
        ]:
            _block("WARMUP_ORDER")
        for fixture in fixture_manifest["fixtures"]:
            subset = [row for row in measured if row["epoch"] == epoch and row["fixture_id"] == fixture["fixture_id"]]
            if [(row["candidate_id"], row["repetition"], row["physical_position"]) for row in subset] != [
                ("A", 1, 1), ("B", 1, 2), ("B", 2, 1), ("A", 2, 2)
            ]:
                _block("ABBA_SCHEDULE_VIOLATION")


def verify_metrics_rows(metric_rows: list[dict[str, Any]], schedule: dict[str, Any]) -> None:
    if any(not isinstance(row, dict) or row.get("phase") != "measured" for row in metric_rows):
        _block("WARMUP_IN_METRICS")
    expected = [
        (row["epoch"], row["fixture_id"], row["candidate_id"], row["repetition"], row["physical_position"])
        for row in schedule["rows"] if row["phase"] == "measured"
    ]
    observed = [
        (row.get("epoch"), row.get("fixture_id"), row.get("candidate_id"), row.get("repetition"), row.get("physical_position"))
        for row in metric_rows
    ]
    if observed != expected:
        _block("METRICS_ROW_SET")


def validate_epoch_set(epoch_receipts: list[dict[str, Any]]) -> None:
    if len(epoch_receipts) != 5 or [item.get("epoch") for item in epoch_receipts] != [1, 2, 3, 4, 5]:
        _block("EPOCH_SET")
    if any(item.get("valid") is not True or item.get("aborted_run_count") != 0 for item in epoch_receipts):
        _block("INVALID_EPOCH_CHERRY_PICK")


def validate_cooldown(start_monotonic_ns: int, end_monotonic_ns: int, minimum_seconds: int = 15) -> int:
    if type(start_monotonic_ns) is not int or type(end_monotonic_ns) is not int or start_monotonic_ns <= 0:
        _block("COOLDOWN_CLOCK")
    elapsed = end_monotonic_ns - start_monotonic_ns
    if elapsed < minimum_seconds * 1_000_000_000:
        _block("COOLDOWN_CONFIG_NOT_ELAPSED")
    return elapsed


def _row(policy: dict[str, Any], candidates: dict[str, dict[str, Any]], epoch: int, fixture: dict[str, str], candidate_id: str, phase: str, repetition: int, position: int) -> dict[str, Any]:
    candidate = candidates[candidate_id]
    material = f"{epoch}|{fixture['task_id']}|{fixture['fixture_id']}|{candidate_id}|{phase}|{repetition}|{position}".encode()
    seed = int.from_bytes(hmac.new(str(policy["bootstrap_seed"]).encode(), material, hashlib.sha256).digest()[:6], "big")
    return {
        "epoch": epoch,
        "task_id": fixture["task_id"],
        "fixture_id": fixture["fixture_id"],
        "candidate_id": candidate_id,
        "model_manifest_sha256": candidate["model_manifest_sha256"],
        "runtime_config_sha256": candidate["runtime_config_sha256"],
        "phase": phase,
        "repetition": repetition,
        "physical_position": position,
        "deterministic_seed": seed,
    }


def _block(detail: str, exit_code: ExitCode = ExitCode.PROTOCOL) -> None:
    raise GateError(FailClass.SCHEDULE, detail, exit_code=exit_code)
