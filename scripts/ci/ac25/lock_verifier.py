"""§7 잠금 검증기 + §4 후보 잠금 계약(엄격 로더).

expected_head 와 expected_tree 는 기본값을 두지 않는다.
scope_end 는 호출자가 고르지 않고 잠금에서 유도한다.
GITHUB_SHA 를 expected head 기본값으로 쓰지 않는다.
모든 실패는 최소 한 개의 구조화된 FailureEvidence 를 남긴다.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone

# ── 실패 코드 (§7) ─────────────────────────────────────────────────────
LOCK_EXPECTED_HEAD_REQUIRED = "LOCK_EXPECTED_HEAD_REQUIRED"
LOCK_EXPECTED_TREE_REQUIRED = "LOCK_EXPECTED_TREE_REQUIRED"
LOCK_HEAD_MISMATCH = "LOCK_HEAD_MISMATCH"
LOCK_TREE_MISMATCH = "LOCK_TREE_MISMATCH"
LOCK_BASE_TREE_MISMATCH = "LOCK_BASE_TREE_MISMATCH"
LOCK_HEAD_TREE_MISMATCH = "LOCK_HEAD_TREE_MISMATCH"
LOCK_SCOPE_END_NOT_CANDIDATE_HEAD = "LOCK_SCOPE_END_NOT_CANDIDATE_HEAD"
LOCK_APPROVED_BASE_MUTATED = "LOCK_APPROVED_BASE_MUTATED"
LOCK_SCHEMA_INVALID = "LOCK_SCHEMA_INVALID"
LOCK_DUPLICATE_KEY = "LOCK_DUPLICATE_KEY"
LOCK_EXPIRED = "LOCK_EXPIRED"
GIT_OBJECT_NOT_FOUND = "GIT_OBJECT_NOT_FOUND"
GIT_ANCESTRY_INVALID = "GIT_ANCESTRY_INVALID"
CHANGED_PATHS_UNAVAILABLE = "CHANGED_PATHS_UNAVAILABLE"
CHANGED_PATH_OUTSIDE_ALLOWLIST = "CHANGED_PATH_OUTSIDE_ALLOWLIST"

_OID_RE = re.compile(r"^[0-9a-f]{40}$")
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_REQUIRED_FIELDS = (
    "schema_version", "repository", "pr_number",
    "approved_base_commit", "approved_base_tree",
    "approved_head_commit", "approved_head_tree",
    "allowed_paths", "identity_manifest_sha256",
    "identity_artifact_zip_sha256", "created_at", "expires_at",
)
_SCHEMA_VERSION = "butler.ac25.candidate_lock.v1"


# ── 데이터 계약 (§7) ───────────────────────────────────────────────────
@dataclass(frozen=True)
class FailureEvidence:
    code: str
    message: str
    expected: str | None = None
    observed: str | None = None
    paths: tuple[str, ...] = ()


@dataclass(frozen=True)
class LockVerdict:
    ok: bool
    failures: tuple[FailureEvidence, ...]
    changed_paths: tuple[str, ...]
    offending_paths: tuple[str, ...]
    scope_start: str
    scope_end: str
    candidate_commit: str
    candidate_tree: str
    execution_commit: str
    execution_tree: str


@dataclass(frozen=True)
class CandidateLock:
    schema_version: str
    repository: str
    pr_number: int
    approved_base_commit: str
    approved_base_tree: str
    approved_head_commit: str
    approved_head_tree: str
    allowed_paths: tuple[str, ...]
    identity_manifest_sha256: str
    identity_artifact_zip_sha256: str
    created_at: datetime
    expires_at: datetime


class LockSchemaError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(f"{code}: {message}")
        self.code = code
        self.message = message


# ── 시각 주입점(시험이 monkeypatch) ────────────────────────────────────
def _now() -> datetime:
    return datetime.now(timezone.utc)


# ── 엄격 JSON 로더 (§4) ────────────────────────────────────────────────
def _no_duplicate_keys(pairs):
    seen = {}
    for k, v in pairs:
        if k in seen:
            raise LockSchemaError(LOCK_DUPLICATE_KEY, f"중복 키: {k}")
        seen[k] = v
    return seen


def _parse_utc(field_name: str, value) -> datetime:
    if not isinstance(value, str):
        raise LockSchemaError(LOCK_SCHEMA_INVALID, f"{field_name} 은 문자열 시각이어야 함")
    if not value.endswith("Z"):
        raise LockSchemaError(LOCK_SCHEMA_INVALID, f"{field_name} 은 UTC('Z') 여야 함: {value}")
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise LockSchemaError(LOCK_SCHEMA_INVALID, f"{field_name} 시각 파싱 실패: {value}") from exc
    if dt.tzinfo is None or dt.utcoffset() != timezone.utc.utcoffset(None):
        raise LockSchemaError(LOCK_SCHEMA_INVALID, f"{field_name} 은 UTC 여야 함: {value}")
    return dt


def _canon_path(p: str) -> str:
    if not isinstance(p, str) or not p:
        raise LockSchemaError(LOCK_SCHEMA_INVALID, f"빈/비문자열 allowed_path: {p!r}")
    if p.startswith("/"):
        raise LockSchemaError(LOCK_SCHEMA_INVALID, f"절대 경로: {p}")
    if "\\" in p:
        raise LockSchemaError(LOCK_SCHEMA_INVALID, f"역슬래시 경로: {p}")
    segs = p.split("/")
    if any(s in ("", ".", "..") for s in segs):
        raise LockSchemaError(LOCK_SCHEMA_INVALID, f".·..·빈 세그먼트: {p}")
    return p


def load_candidate_lock(raw_bytes: bytes) -> CandidateLock:
    """원문 바이트에서 후보 잠금을 엄격 로드. 위반 시 LockSchemaError."""
    try:
        text = raw_bytes.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise LockSchemaError(LOCK_SCHEMA_INVALID, f"UTF-8 디코딩 실패: {exc}") from exc
    try:
        obj = json.loads(text, object_pairs_hook=_no_duplicate_keys)
    except LockSchemaError:
        raise
    except json.JSONDecodeError as exc:
        raise LockSchemaError(LOCK_SCHEMA_INVALID, f"JSON 파싱 실패: {exc}") from exc
    if not isinstance(obj, dict):
        raise LockSchemaError(LOCK_SCHEMA_INVALID, "최상위는 객체여야 함")

    missing = [f for f in _REQUIRED_FIELDS if f not in obj]
    if missing:
        raise LockSchemaError(LOCK_SCHEMA_INVALID, f"필수 필드 누락: {missing}")
    unknown = [k for k in obj if k not in _REQUIRED_FIELDS]
    if unknown:
        raise LockSchemaError(LOCK_SCHEMA_INVALID, f"알 수 없는 필드: {unknown}")

    if obj["schema_version"] != _SCHEMA_VERSION:
        raise LockSchemaError(LOCK_SCHEMA_INVALID, f"schema_version 불일치: {obj['schema_version']}")
    # commit·tree 는 40자 Git OID(sha1)
    for f in ("approved_base_commit", "approved_head_commit",
              "approved_base_tree", "approved_head_tree"):
        if not _OID_RE.match(str(obj[f])):
            raise LockSchemaError(LOCK_SCHEMA_INVALID, f"{f} 은 40자 소문자 hex OID 여야 함: {obj[f]}")
    # identity digest 는 64자 SHA-256
    for f in ("identity_manifest_sha256", "identity_artifact_zip_sha256"):
        if not _SHA256_RE.match(str(obj[f])):
            raise LockSchemaError(LOCK_SCHEMA_INVALID, f"{f} 은 64자 소문자 hex 여야 함: {obj[f]}")
    if not isinstance(obj["pr_number"], int) or isinstance(obj["pr_number"], bool):
        raise LockSchemaError(LOCK_SCHEMA_INVALID, "pr_number 는 정수여야 함")

    ap = obj["allowed_paths"]
    if not isinstance(ap, list) or not ap:
        raise LockSchemaError(LOCK_SCHEMA_INVALID, "allowed_paths 는 비어있지 않은 배열이어야 함")
    canon = [_canon_path(p) for p in ap]
    if len(set(canon)) != len(canon):
        raise LockSchemaError(LOCK_SCHEMA_INVALID, "중복 allowed_paths")
    # 정규화 충돌(대소문자만 다른 동일 경로)
    if len({c.lower() for c in canon}) != len(canon):
        raise LockSchemaError(LOCK_SCHEMA_INVALID, "정규화 충돌 경로(대소문자만 상이)")

    created = _parse_utc("created_at", obj["created_at"])
    expires = _parse_utc("expires_at", obj["expires_at"])
    if created >= expires:
        raise LockSchemaError(LOCK_SCHEMA_INVALID, "created_at >= expires_at")

    return CandidateLock(
        schema_version=obj["schema_version"], repository=obj["repository"],
        pr_number=obj["pr_number"],
        approved_base_commit=obj["approved_base_commit"],
        approved_base_tree=obj["approved_base_tree"],
        approved_head_commit=obj["approved_head_commit"],
        approved_head_tree=obj["approved_head_tree"],
        allowed_paths=tuple(canon),
        identity_manifest_sha256=obj["identity_manifest_sha256"],
        identity_artifact_zip_sha256=obj["identity_artifact_zip_sha256"],
        created_at=created, expires_at=expires,
    )


# ── git 헬퍼 ───────────────────────────────────────────────────────────
def _git(repo: str, args: list[str]) -> tuple[int, str, str]:
    p = subprocess.run(["git", "-C", repo, *args], capture_output=True, check=False)
    return p.returncode, p.stdout.decode("utf-8", "replace").strip(), p.stderr.decode("utf-8", "replace").strip()


def _tree_of(repo: str, commit: str) -> str | None:
    rc, out, _ = _git(repo, ["rev-parse", f"{commit}^{{tree}}"])
    return out if rc == 0 else None


# ── 공개 검증기 (§7) ───────────────────────────────────────────────────
def verify_integration_lock(
    *,
    repository_path: str,
    lock_path: str,
    expected_head: str,
    expected_tree: str,
    execution_commit: str,
) -> LockVerdict:
    from . import git_paths  # 지연 import(순환 방지)

    failures: list[FailureEvidence] = []
    changed: tuple[str, ...] = ()
    offending: tuple[str, ...] = ()

    # expected_head / expected_tree 필수(빈 값 거부)
    if not expected_head:
        failures.append(FailureEvidence(LOCK_EXPECTED_HEAD_REQUIRED, "expected_head 필수", expected="<40 hex>", observed=repr(expected_head)))
    if not expected_tree:
        failures.append(FailureEvidence(LOCK_EXPECTED_TREE_REQUIRED, "expected_tree 필수", expected="<64 hex>", observed=repr(expected_tree)))

    # 잠금 로드
    try:
        with open(lock_path, "rb") as fh:
            lock = load_candidate_lock(fh.read())
    except LockSchemaError as exc:
        failures.append(FailureEvidence(exc.code, exc.message))
        return LockVerdict(False, tuple(failures), changed, offending,
                           "", "", "", "", execution_commit, "")

    scope_start = lock.approved_base_commit
    scope_end = lock.approved_head_commit  # §7: 잠금에서 유도

    if scope_end != lock.approved_head_commit:  # 방어적 불변식
        failures.append(FailureEvidence(LOCK_SCOPE_END_NOT_CANDIDATE_HEAD, "scope_end != 후보 head"))

    if _now() > lock.expires_at:
        failures.append(FailureEvidence(LOCK_EXPIRED, "잠금 만료",
                                        expected=f"<= {lock.expires_at.isoformat()}",
                                        observed=_now().isoformat()))

    if expected_head and expected_head != lock.approved_head_commit:
        failures.append(FailureEvidence(LOCK_HEAD_MISMATCH, "expected_head != 잠금 head",
                                        expected=lock.approved_head_commit, observed=expected_head))
    if expected_tree and expected_tree != lock.approved_head_tree:
        failures.append(FailureEvidence(LOCK_TREE_MISMATCH, "expected_tree != 잠금 head tree",
                                        expected=lock.approved_head_tree, observed=expected_tree))

    # 실제 git tree 대조
    base_tree = _tree_of(repository_path, lock.approved_base_commit)
    head_tree = _tree_of(repository_path, lock.approved_head_commit)
    if base_tree is None:
        failures.append(FailureEvidence(GIT_OBJECT_NOT_FOUND, "approved_base_commit 객체 없음",
                                        observed=lock.approved_base_commit))
    elif base_tree != lock.approved_base_tree:
        failures.append(FailureEvidence(LOCK_BASE_TREE_MISMATCH, "base commit 의 실제 tree 불일치",
                                        expected=lock.approved_base_tree, observed=base_tree))
    if head_tree is None:
        failures.append(FailureEvidence(GIT_OBJECT_NOT_FOUND, "approved_head_commit 객체 없음",
                                        observed=lock.approved_head_commit))
    elif head_tree != lock.approved_head_tree:
        failures.append(FailureEvidence(LOCK_HEAD_TREE_MISMATCH, "head commit 의 실제 tree 불일치",
                                        expected=lock.approved_head_tree, observed=head_tree))

    # 조상 관계(head 가 base 의 후손)
    if base_tree is not None and head_tree is not None:
        rc, _, _ = _git(repository_path, ["merge-base", "--is-ancestor", scope_start, scope_end])
        if rc != 0:
            failures.append(FailureEvidence(GIT_ANCESTRY_INVALID, "head 가 base 의 후손이 아님",
                                            expected=f"ancestor {scope_start}", observed=scope_end))
        else:
            # 변경 경로 계산 + 허용목록
            try:
                changed = git_paths.compute_changed_paths(
                    repository_path=repository_path,
                    base_commit=scope_start, head_commit=scope_end)
                res = git_paths.paths_outside_allowlist(changed, lock.allowed_paths)
                offending = res.offending
                if offending:
                    failures.append(FailureEvidence(
                        CHANGED_PATH_OUTSIDE_ALLOWLIST,
                        "허용 목록 밖 변경 경로", paths=offending))
            except git_paths.GitPathsError as exc:
                failures.append(FailureEvidence(exc.code, exc.message))

    return LockVerdict(
        ok=not failures, failures=tuple(failures),
        changed_paths=changed, offending_paths=offending,
        scope_start=scope_start, scope_end=scope_end,
        candidate_commit=lock.approved_head_commit,
        candidate_tree=lock.approved_head_tree,
        execution_commit=execution_commit,
        execution_tree=head_tree or "",
    )


def _main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="AC-25 lock verifier")
    parser.add_argument("--repository-path", required=True)
    parser.add_argument("--lock-path", required=True)
    parser.add_argument("--expected-head", required=True)
    parser.add_argument("--expected-tree", required=True)
    parser.add_argument("--execution-commit", required=True)
    args = parser.parse_args(argv)
    verdict = verify_integration_lock(
        repository_path=args.repository_path, lock_path=args.lock_path,
        expected_head=args.expected_head, expected_tree=args.expected_tree,
        execution_commit=args.execution_commit)
    print(json.dumps({
        "ok": verdict.ok,
        "failures": [f.__dict__ for f in verdict.failures],
        "changed_path_count": len(verdict.changed_paths),
        "offending_paths": list(verdict.offending_paths),
        "scope_start": verdict.scope_start, "scope_end": verdict.scope_end,
    }, ensure_ascii=False, indent=2))
    return 0 if verdict.ok else 1


if __name__ == "__main__":
    raise SystemExit(_main(sys.argv[1:]))
