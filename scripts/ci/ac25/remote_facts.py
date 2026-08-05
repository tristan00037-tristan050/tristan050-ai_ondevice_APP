"""§E6-1 원격 사실 재확인.

자체 꾸러미 안의 값만 대조하는 것은 내부 정합성 확인일 뿐이다. 단계 B 검증기는
아래를 GitHub API 로 그 자리에서 다시 읽는다.

    PR #903 의 head sha 와 head tree
    승인 커밋의 존재와 committer 시각
    승인 문서와 서명 파일의 원문 바이트
    workflow run 의 시작 시각
    승인자 login 의 실제 계정 ID

읽지 못하면 통과시키지 않는다. 판정 경로에 assert 를 쓰지 않는다(§E6-2).

전송 계층은 주입받는다(테스트가 네트워크 없이 돌 수 있어야 하므로). 다만
★무엇을 읽을지는 이 모듈이 정한다. 부르는 쪽이 값을 직접 넣지 못한다.
"""
from __future__ import annotations

import base64
import binascii
import json
import re
import subprocess
from dataclasses import dataclass
from typing import Protocol

from .cross_track_approval import RemoteFacts

REMOTE_FACT_UNAVAILABLE = "REMOTE_FACT_UNAVAILABLE"

_OID_RE = re.compile(r"^[0-9a-f]{40}$")
_UTC_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")


class Transport(Protocol):
    """GitHub REST 한 건을 읽어 JSON 으로 돌려준다. 실패하면 None."""

    def __call__(self, path: str) -> dict | list | None: ...


@dataclass(frozen=True)
class RemoteFactError:
    code: str
    message: str
    expected: str | None = None
    observed: str | None = None


def gh_transport(path: str) -> dict | list | None:
    """gh CLI 로 읽는 기본 전송. 실패는 None 으로 닫는다."""
    completed = subprocess.run(
        ["gh", "api", path],
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        return None
    try:
        return json.loads(completed.stdout)
    except json.JSONDecodeError:
        return None


def _to_utc_second(value: object) -> str | None:
    """GitHub 시각(…Z 또는 +09:00)을 초 단위 UTC 문자열로 정규화한다."""
    if not isinstance(value, str) or not value:
        return None
    from datetime import datetime, timezone

    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return None
    return parsed.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _decode_content(payload: object) -> bytes | None:
    if not isinstance(payload, dict):
        return None
    content = payload.get("content")
    if not isinstance(content, str):
        return None
    try:
        return base64.b64decode(content, validate=False)
    except (binascii.Error, ValueError):
        return None


def read_candidate_head(
    *, transport: Transport, repository: str, pr_number: int
) -> tuple[str | None, str | None]:
    """PR head 의 sha 와 tree 를 원격에서 읽는다."""
    pull = transport(f"repos/{repository}/pulls/{pr_number}")
    if not isinstance(pull, dict):
        return None, None
    head = pull.get("head")
    if not isinstance(head, dict):
        return None, None
    sha = head.get("sha")
    if not isinstance(sha, str) or not _OID_RE.match(sha):
        return None, None
    commit = transport(f"repos/{repository}/git/commits/{sha}")
    if not isinstance(commit, dict):
        return sha, None
    tree = commit.get("tree")
    tree_sha = tree.get("sha") if isinstance(tree, dict) else None
    if not isinstance(tree_sha, str) or not _OID_RE.match(tree_sha):
        return sha, None
    return sha, tree_sha


def collect_remote_facts(
    *,
    transport: Transport,
    approval_repository: str,
    approval_commit_sha: str,
    document_path: str,
    signature_path: str,
    allowed_signers_path: str,
    approver_login: str,
    run_repository: str,
    run_id: int,
) -> tuple[RemoteFacts | None, tuple[RemoteFactError, ...]]:
    """§E6-1 대상을 모두 읽는다. 하나라도 못 읽으면 그 사실을 증거로 남긴다."""
    errors: list[RemoteFactError] = []

    commit = transport(f"repos/{approval_repository}/commits/{approval_commit_sha}")
    fetchable = isinstance(commit, dict) and isinstance(commit.get("sha"), str)
    committer_utc = ""
    if fetchable:
        commit_body = commit.get("commit") if isinstance(commit, dict) else None
        committer = commit_body.get("committer") if isinstance(commit_body, dict) else None
        normalized = _to_utc_second(committer.get("date") if isinstance(committer, dict) else None)
        if normalized is None:
            errors.append(
                RemoteFactError(
                    REMOTE_FACT_UNAVAILABLE,
                    "승인 커밋 committer 시각을 읽지 못했다",
                    expected="…Z 형식 UTC",
                    observed=str(committer),
                )
            )
        else:
            committer_utc = normalized
    else:
        errors.append(
            RemoteFactError(
                REMOTE_FACT_UNAVAILABLE,
                "승인 커밋을 가져오지 못했다",
                expected=approval_commit_sha,
                observed="fetch 실패",
            )
        )

    # 보호 ref 에서 도달 가능한지 — 커밋 목록에 포함되는지로 확인한다
    reachable = False
    if fetchable:
        listed = transport(
            f"repos/{approval_repository}/commits?sha={approval_commit_sha}&per_page=1"
        )
        reachable = isinstance(listed, list) and len(listed) >= 1

    def _read(path: str, label: str) -> bytes | None:
        payload = transport(
            f"repos/{approval_repository}/contents/{path}?ref={approval_commit_sha}"
        )
        data = _decode_content(payload)
        if data is None:
            errors.append(
                RemoteFactError(
                    REMOTE_FACT_UNAVAILABLE,
                    f"{label} 원문 바이트를 읽지 못했다",
                    expected=path,
                    observed="없음",
                )
            )
        return data

    document_bytes = _read(document_path, "승인 문서")
    signature_bytes = _read(signature_path, "서명 파일")
    allowed_signers_bytes = _read(allowed_signers_path, "allowed_signers")

    run = transport(f"repos/{run_repository}/actions/runs/{run_id}")
    run_started = _to_utc_second(run.get("run_started_at") if isinstance(run, dict) else None)
    if run_started is None:
        errors.append(
            RemoteFactError(
                REMOTE_FACT_UNAVAILABLE,
                "workflow run 시작 시각을 읽지 못했다",
                expected=f"runs/{run_id}.run_started_at",
                observed="없음",
            )
        )
        run_started = ""

    user = transport(f"users/{approver_login}")
    approver_id = user.get("id") if isinstance(user, dict) else None
    if not isinstance(approver_id, int):
        errors.append(
            RemoteFactError(
                REMOTE_FACT_UNAVAILABLE,
                "승인자 계정 ID 를 읽지 못했다",
                expected=f"users/{approver_login}.id",
                observed=str(approver_id),
            )
        )
        approver_id = None

    facts = RemoteFacts(
        approval_commit_fetchable=fetchable,
        approval_commit_reachable=reachable,
        approval_committer_utc=committer_utc,
        run_started_at=run_started,
        document_bytes=document_bytes,
        signature_bytes=signature_bytes,
        allowed_signers_bytes=allowed_signers_bytes,
        approver_id_for_login=approver_id,
    )
    return facts, tuple(errors)


__all__ = [
    "REMOTE_FACT_UNAVAILABLE",
    "RemoteFactError",
    "Transport",
    "collect_remote_facts",
    "gh_transport",
    "read_candidate_head",
]
