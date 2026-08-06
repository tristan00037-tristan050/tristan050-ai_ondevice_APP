"""§5 R6-2 — 단계 B 기대 좌표의 ★단일 원본★ loader (Python).

같은 값을 두 곳에 적으면 한쪽만 고쳐지고, 그 순간 "영수증과 실제가 다름" 이
다시 생긴다. 그래서 기대 좌표의 원본은 stage_b_coordinates.v1.json 하나이고,
Python·Node loader 는 ★값을 복제하지 않고 그 파일만 읽는다★.

계약(§5-1)
    정확히 여섯 키 · 알 수 없는 키 0 · 누락 키 0 · 중복 키 0
    canonical UTF-8 JSON + 끝 newline
    parse 후 정해진 indent·key 순서로 재직렬화한 bytes 가 원본과 완전히 같을 것
      → 중복 키·비정규 표기·공백 장난을 전부 거부한다

★부르는 쪽이 값을 넣을 수 없다. 경로 인자도 없다. workflow·env·CLI 가
  기대값을 덮어쓰는 경로를 만들지 않는다(§5-1 · §9-2).
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType

STAGE_B_COORDINATE_CONTRACT_INVALID = "STAGE_B_COORDINATE_CONTRACT_INVALID"

SCHEMA_VERSION = "butler.ac25.stage_b_coordinates.v1"
COORDINATE_FILENAME = "stage_b_coordinates.v1.json"

# ★key 순서는 계약이다. 재직렬화 대조가 이 순서를 쓴다.
_KEY_ORDER = (
    "schema_version",
    "candidate_commit",
    "candidate_tree",
    "integration_base",
    "merge_commit",
    "merge_tree",
)
_OID_KEYS = _KEY_ORDER[1:]
_OID_RE = re.compile(r"\A[0-9a-f]{40}\Z")
_ALL_ZERO_OID = "0" * 40


class CoordinateContractError(Exception):
    """계약 위반. 메시지에 원문 전체를 넣지 않는다(§5-2)."""

    def __init__(self, code: str = STAGE_B_COORDINATE_CONTRACT_INVALID) -> None:
        super().__init__(code)
        self.code = code


@dataclass(frozen=True)
class StageBCoordinates:
    schema_version: str
    candidate_commit: str
    candidate_tree: str
    integration_base: str
    merge_commit: str
    merge_tree: str

    @property
    def expected_merge_parents(self) -> tuple[str, str]:
        """합성 병합의 부모는 [integration_base, candidate_commit] ★이 순서★ 다."""
        return (self.integration_base, self.candidate_commit)

    def as_mapping(self):
        return MappingProxyType({key: getattr(self, key) for key in _KEY_ORDER})


def coordinate_path() -> Path:
    """단일 원본의 위치. 인자를 받지 않는다 — 부르는 쪽이 고를 수 없다."""
    return Path(__file__).resolve().parent / COORDINATE_FILENAME


def canonical_bytes(mapping) -> bytes:
    """정해진 indent(2)·key 순서로 직렬화한 canonical 표현."""
    ordered = {key: mapping[key] for key in _KEY_ORDER}
    return (json.dumps(ordered, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def _reject_duplicate_keys(pairs: list[tuple[str, object]]) -> dict:
    seen: dict = {}
    for key, value in pairs:
        if key in seen:
            raise CoordinateContractError()
        seen[key] = value
    return seen


def load_from_bytes(raw: bytes) -> StageBCoordinates:
    """원문 바이트에서 좌표를 엄격 로드한다. 위반은 전부 계약 오류다."""
    if not isinstance(raw, (bytes, bytearray)) or not raw:
        raise CoordinateContractError()
    try:
        text = bytes(raw).decode("utf-8")
    except UnicodeDecodeError as exc:
        raise CoordinateContractError() from exc
    try:
        parsed = json.loads(text, object_pairs_hook=_reject_duplicate_keys)
    except CoordinateContractError:
        raise
    except json.JSONDecodeError as exc:
        raise CoordinateContractError() from exc
    if not isinstance(parsed, dict) or set(parsed) != set(_KEY_ORDER):
        raise CoordinateContractError()
    for key in _KEY_ORDER:
        if not isinstance(parsed[key], str):
            raise CoordinateContractError()
    if parsed["schema_version"] != SCHEMA_VERSION:
        raise CoordinateContractError()
    for key in _OID_KEYS:
        value = parsed[key]
        if _OID_RE.match(value) is None or value == _ALL_ZERO_OID:
            raise CoordinateContractError()
    # ★canonical 재직렬화 대조 — 비정규 표기·공백 장난을 거부한다
    if canonical_bytes(parsed) != bytes(raw):
        raise CoordinateContractError()
    return StageBCoordinates(**{key: parsed[key] for key in _KEY_ORDER})


def load_coordinates() -> StageBCoordinates:
    """단일 원본 파일에서 읽는다. 읽지 못하면 통과시키지 않는다."""
    try:
        raw = coordinate_path().read_bytes()
    except OSError as exc:
        raise CoordinateContractError() from exc
    return load_from_bytes(raw)


def coordinate_source_sha256() -> str:
    """영수증에 남길 단일 원본 파일의 지문(§5-3). 원문은 남기지 않는다."""
    import hashlib

    try:
        return hashlib.sha256(coordinate_path().read_bytes()).hexdigest()
    except OSError as exc:
        raise CoordinateContractError() from exc


# ── 잠금과의 일치 강제 ─────────────────────────────────────────────────
COORDINATE_LOCK_DIVERGENCE = "COORDINATE_LOCK_DIVERGENCE"


@dataclass(frozen=True)
class TrustedCoordinates:
    """단계 B 좌표 + 보호된 잠금이 정한 경로 판정 base.

    ★두 원본은 역할이 다르다(§E2). 그러나 겹치는 축(후보 head·tree)은 반드시
      같아야 한다. 어긋나면 통과시키지 않는다 — 그 어긋남이 지난 라운드의
      "영수증과 실제가 다름" 이다.
    """

    stage_b: StageBCoordinates
    provenance_base_commit: str
    provenance_base_tree: str


def load_trusted_coordinates(repository_root: Path | None = None) -> TrustedCoordinates:
    """좌표 단일 원본과 보호된 잠금을 함께 읽고 겹치는 축의 일치를 강제한다."""
    from . import anchors, lock_verifier

    coordinates = load_coordinates()
    root = repository_root or Path(__file__).resolve().parents[3]
    try:
        lock = lock_verifier.load_candidate_lock(
            (root / anchors.CANDIDATE_LOCK_PATH).read_bytes()
        )
    except (OSError, lock_verifier.LockSchemaError) as exc:
        raise CoordinateContractError(COORDINATE_LOCK_DIVERGENCE) from exc

    if (
        lock.approved_head_commit != coordinates.candidate_commit
        or lock.approved_head_tree != coordinates.candidate_tree
    ):
        raise CoordinateContractError(COORDINATE_LOCK_DIVERGENCE)

    return TrustedCoordinates(
        stage_b=coordinates,
        provenance_base_commit=lock.approved_base_commit,
        provenance_base_tree=lock.approved_base_tree,
    )


# ★workflow 가 좌표를 갖지 않게 하는 유일한 통로(§5-1 · §9-2).
#   값은 GITHUB_OUTPUT 파일로만 나간다. 공개 로그에 OID 를 찍지 않는다.
EMITTED_KEYS = (
    "candidate_commit",
    "candidate_tree",
    "integration_base",
    "merge_commit",
    "merge_tree",
    "provenance_base_commit",
    "provenance_base_tree",
    "coordinate_ssot_sha256",
)


def emitted_values(trusted: TrustedCoordinates) -> dict[str, str]:
    stage_b = trusted.stage_b
    return {
        "candidate_commit": stage_b.candidate_commit,
        "candidate_tree": stage_b.candidate_tree,
        "integration_base": stage_b.integration_base,
        "merge_commit": stage_b.merge_commit,
        "merge_tree": stage_b.merge_tree,
        "provenance_base_commit": trusted.provenance_base_commit,
        "provenance_base_tree": trusted.provenance_base_tree,
        "coordinate_ssot_sha256": coordinate_source_sha256(),
    }


# ── §5-2 생산 판정 ─────────────────────────────────────────────────────
CANDIDATE_COMMIT_MISMATCH = "CANDIDATE_COMMIT_MISMATCH"
CANDIDATE_TREE_MISMATCH = "CANDIDATE_TREE_MISMATCH"
INTEGRATION_BASE_MISMATCH = "INTEGRATION_BASE_MISMATCH"
MERGE_COMMIT_MISMATCH = "MERGE_COMMIT_MISMATCH"
MERGE_TREE_MISMATCH = "MERGE_TREE_MISMATCH"
MERGE_PARENT_COUNT_MISMATCH = "MERGE_PARENT_COUNT_MISMATCH"
MERGE_PARENT_ORDER_MISMATCH = "MERGE_PARENT_ORDER_MISMATCH"

# ★§5-2 가 정한 보고 순서. 여러 개면 이 순서대로 모은다.
FAILURE_ORDER = (
    STAGE_B_COORDINATE_CONTRACT_INVALID,
    CANDIDATE_COMMIT_MISMATCH,
    CANDIDATE_TREE_MISMATCH,
    INTEGRATION_BASE_MISMATCH,
    MERGE_COMMIT_MISMATCH,
    MERGE_TREE_MISMATCH,
    MERGE_PARENT_COUNT_MISMATCH,
    MERGE_PARENT_ORDER_MISMATCH,
)


def evaluate_observed(
    *,
    candidate_commit: object,
    candidate_tree: object,
    integration_base: object,
    merge_commit: object,
    merge_tree: object,
    merge_parents: object,
    expected: StageBCoordinates | None = None,
) -> tuple[str, ...]:
    """관측 좌표를 기대 좌표와 ★정확히★ 비교한다. 형식 일치만으로 통과시키지 않는다.

    반환은 FAILURE_ORDER 순의 오류 코드 튜플이다. 빈 튜플이면 통과다.
    """
    try:
        expectation = expected if expected is not None else load_coordinates()
    except CoordinateContractError:
        return (STAGE_B_COORDINATE_CONTRACT_INVALID,)

    codes: list[str] = []

    def _check(observed: object, want: str, code: str) -> None:
        if not isinstance(observed, str) or _OID_RE.match(observed) is None:
            codes.append(code)
        elif observed != want:
            codes.append(code)

    _check(candidate_commit, expectation.candidate_commit, CANDIDATE_COMMIT_MISMATCH)
    _check(candidate_tree, expectation.candidate_tree, CANDIDATE_TREE_MISMATCH)
    _check(integration_base, expectation.integration_base, INTEGRATION_BASE_MISMATCH)
    _check(merge_commit, expectation.merge_commit, MERGE_COMMIT_MISMATCH)
    _check(merge_tree, expectation.merge_tree, MERGE_TREE_MISMATCH)

    if not isinstance(merge_parents, (list, tuple)):
        codes.append(MERGE_PARENT_COUNT_MISMATCH)
    else:
        parents = list(merge_parents)
        if len(parents) != 2:
            codes.append(MERGE_PARENT_COUNT_MISMATCH)
        elif tuple(parents) != expectation.expected_merge_parents:
            codes.append(MERGE_PARENT_ORDER_MISMATCH)

    order = {code: index for index, code in enumerate(FAILURE_ORDER)}
    return tuple(sorted(dict.fromkeys(codes), key=lambda code: order[code]))


def _emit_main(argv: list[str]) -> int:
    """`python3 -m ac25.stage_b_coordinates --emit-github-output`.

    ★값은 GITHUB_OUTPUT 파일에만 쓴다. stdout 은 VERDICT·ERROR_CODE 두 줄이다.
    ★경로·좌표 인자를 받지 않는다. 부르는 쪽이 기대값을 고를 수 없다.
    """
    import argparse
    import os

    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--emit-github-output", action="store_true")
    try:
        parser.parse_args(argv)
    except SystemExit:
        print("VERDICT=0")
        print(f"ERROR_CODE={STAGE_B_COORDINATE_CONTRACT_INVALID}")
        return 1

    try:
        values = emitted_values(load_trusted_coordinates())
    except CoordinateContractError as exc:
        print("VERDICT=0")
        print(f"ERROR_CODE={exc.code}")
        return 1

    target = os.environ.get("GITHUB_OUTPUT")
    if not target:
        print("VERDICT=0")
        print(f"ERROR_CODE={STAGE_B_COORDINATE_CONTRACT_INVALID}")
        return 1
    try:
        with open(target, "a", encoding="utf-8") as stream:
            for key in EMITTED_KEYS:
                stream.write(f"{key}={values[key]}\n")
    except OSError:
        print("VERDICT=0")
        print(f"ERROR_CODE={STAGE_B_COORDINATE_CONTRACT_INVALID}")
        return 1
    print("VERDICT=1")
    print("ERROR_CODE=OK")
    return 0


if __name__ == "__main__":
    import sys as _sys

    raise SystemExit(_emit_main(_sys.argv[1:]))


__all__ = [
    "CANDIDATE_COMMIT_MISMATCH",
    "COORDINATE_LOCK_DIVERGENCE",
    "EMITTED_KEYS",
    "TrustedCoordinates",
    "emitted_values",
    "load_trusted_coordinates",
    "CANDIDATE_TREE_MISMATCH",
    "COORDINATE_FILENAME",
    "CoordinateContractError",
    "FAILURE_ORDER",
    "INTEGRATION_BASE_MISMATCH",
    "MERGE_COMMIT_MISMATCH",
    "MERGE_PARENT_COUNT_MISMATCH",
    "MERGE_PARENT_ORDER_MISMATCH",
    "MERGE_TREE_MISMATCH",
    "SCHEMA_VERSION",
    "STAGE_B_COORDINATE_CONTRACT_INVALID",
    "StageBCoordinates",
    "canonical_bytes",
    "coordinate_path",
    "coordinate_source_sha256",
    "evaluate_observed",
    "load_coordinates",
    "load_from_bytes",
]
