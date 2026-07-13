from __future__ import annotations

import hashlib
import json
import random
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Literal

FIXTURE_SCHEMA = "butler.model_tier_fixture.v2"
PROTOCOL_SCHEMA = "butler.model_tier_benchmark_protocol.v2"
SUBJECT_APP_SHA = "20f7da05a66dfa8559859851555403be4ea00da5"
SHA256_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
BUILD_SHA_RE = re.compile(r"^[0-9a-f]{40}$")

BoxId = Literal["1", "3"]
CandidateId = Literal[
    "box1_rule_model_none",
    "main_4b_general",
    "box3_1p7_v9_2_r2b",
    "box3_4b_repair",
]
RunKind = Literal["process_cold", "warm"]

ROLE_MATRIX: dict[str, frozenset[str]] = {
    "1": frozenset({"box1_rule_model_none", "main_4b_general"}),
    "3": frozenset({"box3_1p7_v9_2_r2b", "box3_4b_repair"}),
}
MODEL_PHYSICAL_KEY: dict[str, str] = {
    "main_4b_general": "main_qwen3_4b_q4_k_m",
    "box3_4b_repair": "main_qwen3_4b_q4_k_m",
    "box3_1p7_v9_2_r2b": "box3_v9_2_r2b_1p7_q4_k_m",
    "box1_rule_model_none": "MODEL_NONE",
}
ALLOWED_BUCKETS = {
    "1": frozenset({"simple", "ambiguous", "multi_intent_attachment"}),
    "3": frozenset({"short", "medium", "long_multi_evidence"}),
}


def stable_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def stable_digest(value: Any) -> str:
    return "sha256:" + hashlib.sha256(stable_json(value).encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class FixtureV2:
    schema_version: str
    fixture_id: str
    box_id: BoxId
    complexity_bucket: str
    synthetic: bool
    fixture_payload: dict[str, Any]
    input_digest: str
    expected: dict[str, Any]

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "FixtureV2":
        required = {
            "schema_version", "fixture_id", "box_id", "complexity_bucket",
            "synthetic", "fixture_payload", "input_digest", "expected",
        }
        if set(payload) != required:
            raise ValueError("FIXTURE_EXACT_KEYS_REQUIRED")
        fixture = cls(**payload)
        fixture.validate()
        return fixture

    def validate(self) -> None:
        if self.schema_version != FIXTURE_SCHEMA:
            raise ValueError("FIXTURE_SCHEMA_INVALID")
        if self.box_id not in ROLE_MATRIX:
            raise ValueError("FIXTURE_BOX_INVALID")
        if self.complexity_bucket not in ALLOWED_BUCKETS[self.box_id]:
            raise ValueError("FIXTURE_BUCKET_INVALID")
        if not re.fullmatch(r"[A-Za-z0-9_.-]{1,128}", self.fixture_id):
            raise ValueError("FIXTURE_ID_INVALID")
        if self.synthetic is not True:
            raise ValueError("FIXTURE_SYNTHETIC_REQUIRED")
        if not isinstance(self.fixture_payload, dict) or not isinstance(self.expected, dict):
            raise ValueError("FIXTURE_OBJECT_INVALID")
        if not SHA256_RE.fullmatch(self.input_digest):
            raise ValueError("FIXTURE_DIGEST_INVALID")
        if self.input_digest != stable_digest(self.fixture_payload):
            raise ValueError("FIXTURE_DIGEST_MISMATCH")


@dataclass(frozen=True)
class ProtocolConfigV2:
    schema_version: str = PROTOCOL_SCHEMA
    subject_app_sha: str = SUBJECT_APP_SHA
    cold_repetitions: int = 3
    warmup_repetitions: int = 2
    warm_repetitions: int = 10
    cooldown_seconds: float = 15.0
    memory_sample_interval_ms: int = 20
    seeded_shuffle: int = 20260713
    percentile_method: str = "linear_interpolation_v1"
    external_send_zero: bool = True
    runtime_activation_allowed: bool = False

    def validate(self) -> None:
        if self.schema_version != PROTOCOL_SCHEMA:
            raise ValueError("PROTOCOL_SCHEMA_INVALID")
        if not BUILD_SHA_RE.fullmatch(self.subject_app_sha):
            raise ValueError("SUBJECT_APP_SHA_INVALID")
        if self.cold_repetitions != 3 or self.warmup_repetitions < 2 or self.warm_repetitions < 10:
            raise ValueError("REPETITION_CONTRACT_INVALID")
        if self.cooldown_seconds < 15.0:
            raise ValueError("COOLDOWN_CONTRACT_INVALID")
        if not 1 <= self.memory_sample_interval_ms <= 20:
            raise ValueError("MEMORY_SAMPLE_INTERVAL_INVALID")
        if self.percentile_method != "linear_interpolation_v1":
            raise ValueError("PERCENTILE_METHOD_INVALID")
        if self.external_send_zero is not True or self.runtime_activation_allowed is not False:
            raise ValueError("PROTOCOL_SAFETY_INVARIANT_INVALID")

    @property
    def digest(self) -> str:
        self.validate()
        return stable_digest(asdict(self))


@dataclass(frozen=True)
class RunSpec:
    box_id: BoxId
    candidate_id: CandidateId
    fixture_id: str
    run_kind: RunKind
    iteration: int
    measured: bool = True

    @property
    def physical_model_key(self) -> str:
        return MODEL_PHYSICAL_KEY;self.candidate_id]


def validate_role(box_id: str, candidate_id: str) -> None:
    if box_id not in ROLE_MATRIX:
        raise ValueError("UNKNOWN_BOX")
    if candidate_id not in ROLE_MATRIX[box_id]:
        raise ValueError("MODEL_ROLE_MISMATCH")


def load_fixtures(fixture_dir: Path) -> list[FixtureV2]:
    fixtures: list[FixtureV2] = []
    paths = sorted([*fixture_dir.rglob("*.json"), *fixture_dir.rglob("*.jsonl")])
    for path in paths:
        if path.name == "fixture_pack_manifest.json":
            continue
        if path.suffix == ".json":
            payload = json.loads(path.read_text(encoding="utf-8"))
            fixtures.append(FixtureV2.from_dict(payload))
        else:
            for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
                if not line.strip():
                    continue
                try:
                    payload = json.loads(line)
                except json.JSONDecodeError as exc:
                    raise ValueError(f"FIXTURE_JSON_INVALID:{path.name}:{line_no}") from exc
                fixtures.append(FixtureV2.from_dict(payload))
    ids = [item.fixture_id for item in fixtures]
    if len(ids) != len(set(ids)):
        raise ValueError("FIXTURE_ID_DUPLICATE")
    by_box = {box: [item for item in fixtures if item.box_id == box] for box in ROLE_MATRIX}
    for box_id, expected_buckets in ALLOWED_BUCKETS.items():
        rows = by_box[box_id]
        if len(rows) != 30:
            raise ValueError(f"BOX{box_id}_FIXTURE_COUNT_INVALID")
        counts = {bucket: sum(item.complexity_bucket == bucket for item in rows) for bucket in expected_buckets}
        if any(value != 10 for value in counts.values()):
            raise ValueError(f"BOX{box_id}_FIXTURE_BUCKET_COUNT_INVALID")
    manifest_path = fixture_dir / "fixture_pack_manifest.json"
    if manifest_path.is_file():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        required_manifest = {
            "schema_version", "canonical_fixture_pack_digest", "fixture_count",
            "subject_app_sha", "synthetic_only", "runtime_activation_allowed",
            "files", "fixture_pack_file_digest", "raw_text_logged", "external_send_zero",
        }
        if set(manifest) != required_manifest:
            raise ValueError("FIXTURE_MANIFEST_EXACT_KEYS_REQUIRED")
        if manifest["schema_version"] != "butler.model_tier_fixture_pack_manifest.v2":
            raise ValueError("FIXTURE_MANIFEST_SCHEMA_INVALID")
        if manifest["fixture_count"] != len(fixtures):
            raise ValueError("FIXTURE_MANIFEST_COUNT_MISMATCH")
        canonical = stable_digest([asdict(item) for item in sorted(fixtures, key=lambda x: x.fixture_id)])
        if manifest["canonical_fixture_pack_digest"] != canonical:
            raise ValueError("FIXTURE_MANIFEST_CANONICAL_DIGEST_MISMATCH")
        if manifest["subject_app_sha"] != SUBJECT_APP_SHA:
            raise ValueError("FIXTURE_MANIFEST_SUBJECT_SHA_MISMATCH")
        if manifest["synthetic_only"] is not True or manifest["runtime_activation_allowed"] is not False:
            raise ValueError("FIXTURE_MANIFEST_SAFETY_INVALID")
        if manifest["raw_text_logged"] is not False or manifest["external_send_zero"] is not True:
            raise ValueError("FIXTURE_MANIFEST_RAW_ZERO_INVALID")
        listed = manifest["files"]
        data_paths = sorted(path for path in paths if path.name != "fixture_pack_manifest.json")
        if not isinstance(listed, list) or len(listed) != len(data_paths):
            raise ValueError("FIXTURE_MANIFEST_FILES_INVALID")
        expected_relative_paths = {str(path.relative_to(fixture_dir)) for path in data_paths}
        observed_relative_paths: set[str] = set()
        verified_file_digests: list[str] = []
        for entry in listed:
            if not isinstance(entry, dict) or set(entry) != {"path", "sha256"}:
                raise ValueEError("FIXTURE_MANIFEST_FILE_ENTRY_INVALID")
            rel = entry["path"]
            if not isinstance(rel, str) or rel in observed_relative_paths:
                raise ValueError("FIXTURE_MANIFEST_FILE_PATH_INVALID")
            observed_relative_paths.add(rel)
            file_path = fixture_dir / rel
            if not file_path.is_file():
                raise ValueError("FIXTURE_MANIFEST_FILE_MISSING")
            digest = "sha256:" + hashlib.sha256(file_path.read_bytes()).hexdigest()
            if entry["sha256"] != digest:
                raise ValueError("FIXTURE_MANIFEST_FILE_DIGEST_MISMATCH")
            verified_file_digests.append(digest)
        if observed_relative_paths != expected_relative_paths:
            raise ValueError("FIXTURE_MANIFEST_FILE_SET_MISMATCH")
        file_digest = "sha256:" + hashlib.sha256("".join(verified_file_digests).encode("utf-8")).hexdigest()
        if manifest["fixture_pack_file_digest"] != file_digest:
            raise ValueError("FIXTURE_MANIFEST_PACK_FILE_DIGEST_MISMATCH")
    return fixtures


def fixture_pack_digest(fixtures: list[FixtureV2]) -> str:
    return stable_digest([asdict(item) for item in sorted(fixtures, key=lambda x: x.fixture_id)])


def build_plan(fixtures: list[FixtureV2], protocol: ProtocolConfigV2) -> list[RunSpec]:
    """Build a deterministic thermally interleaved 1,206-run plan.

    Process-cold is physical-model-level. Warm runs alternate boxes, candidates,
    and iterations so one bucket/model does not monopolize a long thermal window.
    """
    protocol.validate()
    box1 = sorted((item for item in fixtures if item.box_id == "1"), key=lambda x: x.fixture_id)
    box3 = sorted((item for item in fixtures if item.box_id == "3"), key=lambda x: x.fixture_id)
    if len(box1) != 30 or len(box3) != 30:
        raise ValueError("FIXTURE_MATRIX_INVALID")
    runs: list[RunSpec] = []
    for candidate, box_id, canary in (
        ("main_4b_general", "1", box1[0].fixture_id),
        ("box3_1p7_v9_2_r2b", "3", box3[0].fixture_id),
    ):
        for index in range(protocol.cold_repetitions):
            runs.append(RunSpec(box_id, candidate, canary, "process_cold", index))

    rng = random.Random(protocol.seeded_shuffle)
    shuffled1, shuffled3 = list(box1), list(box3)
    rng.shuffle(shuffled1)
    rng.shuffle(shuffled3)
    pairs = list(zip(shuffled1, shuffled3))
    for iteration in range(protocol.warm_repetitions):
        cycle = pairs if iteration % 2 == 0 else list(reversed(pairs))
        for pair_index, (left, right) in enumerate(cycle):
            box1_candidates = ("box1_rule_model_none", "main_4b_general")
            box3_candidates = ("box3_1p7_v9_2_r2b", "box3_4b_repair")
            if (iteration + pair_index) % 2:
                box1_candidates = tuple(reversed(box1_candidates))
                box3_candidates = tuple(reversed(box3_candidates))
            for fixture, candidates in ((left, box1_candidates), (right, box3_candidates)):
                for candidate in candidates:
                    validate_role(fixture.box_id, candidate)
                    runs.append(
                        RunSpec(
                            fixture.box_id,
                            candidate,
                            fixture.fixture_id,
                            "warm",
                            iteration,
                        )
                    )
    return runs


def expected_run_counts(protocol: ProtocolConfigV2 | None = None) -> dict[str, int]:
    cfg = protocol or ProtocolConfigV2()
    return {
        "process_cold_total": 6,
        "box1_warm_total": 30 * 2 * cfg.warm_repetitions,
        "box3_warm_total": 30 * 2 * cfg.warm_repetitions,
        "total": 6 + 120 * cfg.warm_repetitions,
    }
