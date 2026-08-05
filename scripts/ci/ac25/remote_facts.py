"""§E6-1 원격 사실 재확인.

자체 꾸러미 안의 값만 대조하는 것은 내부 정합성 확인일 뿐이다. 검증기는 아래를
GitHub API 로 그 자리에서 다시 읽는다.

    PR 의 head sha·head tree·base sha
    보호 ref 가 지금 가리키는 커밋(★조상 판정의 기준으로 고정한다)
    승인 커밋이 그 보호 ref 의 ★조상인지
    승인 커밋의 committer 시각
    승인 문서·서명·allowed_signers 의 원문 바이트
    workflow run 의 시작 시각
    승인자 login 의 실제 계정 ID

읽지 못하면 통과시키지 않는다. 판정 경로에 assert 를 쓰지 않는다(§E6-2).

전송 계층은 주입받는다(시험이 네트워크 없이 돌 수 있어야 하므로). 다만
★무엇을 읽을지는 이 모듈이 정한다. 부르는 쪽이 값을 직접 넣지 못한다.

★조상 판정 (정오표 후속 교정)
  이전 판은 `commits?sha=<commit>` 목록이 비지 않는지로 도달 가능을 근사했다.
  그 조회는 "그 커밋에서 시작한 이력"을 돌려줄 뿐이라, 저장소에 존재하기만 하면
  어떤 커밋이든 통과한다. 보호 ref 의 조상임을 전혀 증명하지 못한다.
  근사 검사는 삭제했고, compare API 의 조상 관계 판정으로 대체했다.
      compare/{protected_head}...{commit}  →  status in {behind, identical}
  목록 응답을 조상 근거로 쓰는 경로는 남아 있지 않다(pagination 무관).
"""
from __future__ import annotations

import base64
import binascii
import json
import re
import subprocess
from dataclasses import dataclass, field
from typing import Mapping, Protocol
from urllib.parse import quote

from .cross_track_approval import RemoteFacts

# ── 실패 코드 ──────────────────────────────────────────────────────────
REMOTE_FACT_UNAVAILABLE = "REMOTE_FACT_UNAVAILABLE"
REMOTE_FACT_NOT_FOUND = "REMOTE_FACT_NOT_FOUND"
REMOTE_FACT_FORBIDDEN = "REMOTE_FACT_FORBIDDEN"
REMOTE_FACT_RATE_LIMITED = "REMOTE_FACT_RATE_LIMITED"
REMOTE_FACT_MALFORMED = "REMOTE_FACT_MALFORMED"

_OID_RE = re.compile(r"^[0-9a-f]{40}$")
_STATUS_LINE_RE = re.compile(r"^HTTP/[0-9.]+\s+(\d{3})")

# compare API 에서 head 가 base 의 조상임을 뜻하는 상태
_ANCESTOR_STATES = frozenset({"behind", "identical"})


@dataclass(frozen=True)
class TransportResult:
    """HTTP 한 건의 결과. 상태 코드를 구분해야 404·403·rate-limit 을 나눌 수 있다."""
    status: int
    payload: dict | list | None = None
    headers: Mapping[str, str] = field(default_factory=dict)
    message: str = ""


class Transport(Protocol):
    """GitHub REST 한 건을 읽는다."""

    def __call__(self, path: str) -> TransportResult: ...


@dataclass(frozen=True)
class RemoteFactError:
    code: str
    message: str
    expected: str | None = None
    observed: str | None = None


@dataclass(frozen=True)
class RemoteObservation:
    """원격에서 실측한 사실 일체."""
    facts: RemoteFacts
    protected_ref_head: str      # ★조상 판정의 기준으로 고정한 커밋
    observed_repository: str     # repos/{r} 응답의 full_name
    observed_protected_ref: str  # git/ref/... 응답의 ref
    observed_document_path: str  # contents 응답의 path
    candidate_head_sha: str
    candidate_head_tree: str
    candidate_base_sha: str


def gh_transport(path: str) -> TransportResult:
    """gh CLI 로 읽는 기본 전송. 응답 헤더까지 받아 상태를 구분한다."""
    try:
        completed = subprocess.run(
            ["gh", "api", "-i", path],
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError as exc:
        return TransportResult(status=0, message=f"gh 실행 실패: {exc}")

    raw = completed.stdout.replace("\r\n", "\n")
    head, separator, body = raw.partition("\n\n")
    if not separator:  # 헤더/본문 경계를 찾지 못함
        head, body = "", raw

    status = 0
    headers: dict[str, str] = {}
    for index, line in enumerate(head.splitlines()):
        if index == 0:
            match = _STATUS_LINE_RE.match(line.strip())
            if match is not None:
                status = int(match.group(1))
            continue
        name, sep, value = line.partition(":")
        if sep:
            headers[name.strip().lower()] = value.strip()

    if status == 0:
        return TransportResult(
            status=0,
            headers=headers,
            message=(completed.stderr or "응답 상태를 읽지 못했다").strip(),
        )

    payload: dict | list | None = None
    stripped = body.strip()
    if stripped:
        try:
            payload = json.loads(stripped)
        except json.JSONDecodeError as exc:
            return TransportResult(status=status, headers=headers, message=f"JSON 파싱 실패: {exc}")
    return TransportResult(status=status, payload=payload, headers=headers)


def classify(result: TransportResult) -> str | None:
    """전송 결과를 실패 코드로 분류한다. 정상이면 None."""
    if result.status == 404:
        return REMOTE_FACT_NOT_FOUND
    remaining = str(result.headers.get("x-ratelimit-remaining", "")).strip()
    if result.status == 429 or (result.status == 403 and remaining == "0"):
        return REMOTE_FACT_RATE_LIMITED
    if result.status == 403:
        return REMOTE_FACT_FORBIDDEN
    if result.status < 200 or result.status >= 300:
        return REMOTE_FACT_UNAVAILABLE
    if result.payload is None:
        return REMOTE_FACT_MALFORMED
    return None


class _Reader:
    """전송 결과를 분류하며 읽고, 실패를 증거로 모은다."""

    def __init__(self, transport: Transport) -> None:
        self._transport = transport
        self.errors: list[RemoteFactError] = []

    def object(self, path: str, label: str) -> dict | None:
        result = self._transport(path)
        code = classify(result)
        if code is not None:
            self.errors.append(
                RemoteFactError(
                    code, f"{label} 을(를) 읽지 못했다",
                    expected=path,
                    observed=f"status={result.status} {result.message}".strip(),
                )
            )
            return None
        if not isinstance(result.payload, dict):
            # 목록 응답을 객체로 받아 쓰지 않는다(pagination 오해 차단)
            self.errors.append(
                RemoteFactError(
                    REMOTE_FACT_MALFORMED, f"{label} 응답이 객체가 아니다",
                    expected="JSON 객체",
                    observed=type(result.payload).__name__,
                )
            )
            return None
        return result.payload

    def fail(self, code: str, message: str, expected: str, observed: str) -> None:
        self.errors.append(RemoteFactError(code, message, expected=expected, observed=observed))


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
    if payload.get("encoding") not in (None, "base64"):
        return None
    content = payload.get("content")
    if not isinstance(content, str):
        return None
    try:
        return base64.b64decode(content, validate=False)
    except (binascii.Error, ValueError):
        return None


def _encode_path(path: str) -> str:
    return quote(path, safe="/")


def is_ancestor(
    *, transport: Transport, repository: str, ancestor: str, descendant: str
) -> bool | None:
    """`ancestor` 가 `descendant` 의 조상인지 compare API 로 판정한다.

    compare/{base}...{head} 의 status 는 head 가 base 에 대해 갖는 관계다.
    base=descendant, head=ancestor 로 물으면 behind/identical 이 조상이다.
    판정할 수 없으면 None(= 통과시키지 않음).
    """
    if not _OID_RE.match(ancestor or "") or not _OID_RE.match(descendant or ""):
        return None
    result = transport(f"repos/{repository}/compare/{descendant}...{ancestor}")
    if classify(result) is not None or not isinstance(result.payload, dict):
        return None
    state = result.payload.get("status")
    if not isinstance(state, str):
        return None
    return state in _ANCESTOR_STATES


def read_candidate_head(
    *, transport: Transport, repository: str, pr_number: int
) -> tuple[str | None, str | None, str | None]:
    """PR 의 head sha·head tree·base sha 를 원격에서 읽는다."""
    reader = _Reader(transport)
    pull = reader.object(f"repos/{repository}/pulls/{pr_number}", "PR")
    if pull is None:
        return None, None, None
    head = pull.get("head")
    base = pull.get("base")
    sha = head.get("sha") if isinstance(head, dict) else None
    base_sha = base.get("sha") if isinstance(base, dict) else None
    if not isinstance(sha, str) or not _OID_RE.match(sha):
        return None, None, base_sha if isinstance(base_sha, str) else None
    if not isinstance(base_sha, str) or not _OID_RE.match(base_sha):
        base_sha = None
    commit = reader.object(f"repos/{repository}/git/commits/{sha}", "후보 head 커밋")
    if commit is None:
        return sha, None, base_sha
    tree = commit.get("tree")
    tree_sha = tree.get("sha") if isinstance(tree, dict) else None
    if not isinstance(tree_sha, str) or not _OID_RE.match(tree_sha):
        return sha, None, base_sha
    return sha, tree_sha, base_sha


def read_account_id(
    *, transport: Transport, login: str
) -> tuple[int | None, tuple[RemoteFactError, ...]]:
    """login 의 실제 GitHub 계정 ID 를 조회한다. 문서를 읽은 뒤에 부른다."""
    reader = _Reader(transport)
    if not login:
        reader.fail(
            REMOTE_FACT_MALFORMED, "승인자 login 이 비어 있다",
            expected="승인 문서의 approver_login", observed="(빈 값)",
        )
        return None, tuple(reader.errors)
    user = reader.object(f"users/{quote(login, safe='')}", "승인자 계정")
    if user is None:
        return None, tuple(reader.errors)
    account_id = user.get("id")
    if not isinstance(account_id, int) or isinstance(account_id, bool):
        reader.fail(
            REMOTE_FACT_MALFORMED, "승인자 계정 ID 를 읽지 못했다",
            expected=f"users/{login}.id", observed=str(account_id),
        )
        return None, tuple(reader.errors)
    return account_id, tuple(reader.errors)


def collect_remote_facts(
    *,
    transport: Transport,
    approval_repository: str,
    approval_protected_ref: str,
    approval_commit_sha: str,
    document_path: str,
    signature_path: str,
    allowed_signers_path: str,
    candidate_repository: str,
    pr_number: int,
    run_repository: str,
    run_id: int,
) -> tuple[RemoteObservation, tuple[RemoteFactError, ...]]:
    """§E6-1 대상을 모두 읽는다. 하나라도 못 읽으면 그 사실을 증거로 남긴다."""
    reader = _Reader(transport)

    # ── 승인 저장소 신원(측정값) ──────────────────────────────────────
    repo_payload = reader.object(f"repos/{approval_repository}", "승인 저장소")
    observed_repository = ""
    if repo_payload is not None:
        full_name = repo_payload.get("full_name")
        if isinstance(full_name, str):
            observed_repository = full_name

    # ── 보호 ref 가 지금 가리키는 커밋(조상 판정 기준으로 고정) ────────
    ref_short = approval_protected_ref.removeprefix("refs/")
    ref_payload = reader.object(
        f"repos/{approval_repository}/git/ref/{ref_short}", "보호 ref"
    )
    protected_ref_head = ""
    observed_protected_ref = ""
    if ref_payload is not None:
        observed = ref_payload.get("ref")
        if isinstance(observed, str):
            observed_protected_ref = observed
        obj = ref_payload.get("object")
        head_sha = obj.get("sha") if isinstance(obj, dict) else None
        if isinstance(head_sha, str) and _OID_RE.match(head_sha):
            protected_ref_head = head_sha
        else:
            reader.fail(
                REMOTE_FACT_MALFORMED, "보호 ref 가 가리키는 커밋을 읽지 못했다",
                expected="40자 Git OID", observed=str(head_sha),
            )

    # ── 승인 커밋 ─────────────────────────────────────────────────────
    commit = reader.object(
        f"repos/{approval_repository}/commits/{approval_commit_sha}", "승인 커밋"
    )
    fetchable = commit is not None
    committer_utc = ""
    if commit is not None:
        body = commit.get("commit")
        committer = body.get("committer") if isinstance(body, dict) else None
        normalized = _to_utc_second(committer.get("date") if isinstance(committer, dict) else None)
        if normalized is None:
            reader.fail(
                REMOTE_FACT_MALFORMED, "승인 커밋 committer 시각을 읽지 못했다",
                expected="…Z 형식 UTC", observed=str(committer),
            )
        else:
            committer_utc = normalized

    # ── ★조상 판정 (근사 아님) ────────────────────────────────────────
    reachable = False
    if fetchable and protected_ref_head:
        verdict = is_ancestor(
            transport=transport,
            repository=approval_repository,
            ancestor=approval_commit_sha,
            descendant=protected_ref_head,
        )
        if verdict is None:
            reader.fail(
                REMOTE_FACT_UNAVAILABLE, "승인 커밋의 조상 관계를 판정하지 못했다",
                expected=f"compare/{protected_ref_head}...{approval_commit_sha}",
                observed="판정 불가",
            )
        else:
            reachable = verdict

    # ── 승인 산출물 원문 바이트 (★고정 repo·commit·path 의 API 응답만) ──
    def _read(path: str, label: str) -> tuple[bytes | None, str]:
        payload = reader.object(
            f"repos/{approval_repository}/contents/{_encode_path(path)}"
            f"?ref={approval_commit_sha}",
            label,
        )
        data = _decode_content(payload)
        if data is None:
            reader.fail(
                REMOTE_FACT_MALFORMED, f"{label} 원문 바이트를 해독하지 못했다",
                expected=path, observed="없음",
            )
            return None, ""
        observed_path = payload.get("path") if isinstance(payload, dict) else None
        return data, observed_path if isinstance(observed_path, str) else ""

    document_bytes, observed_document_path = _read(document_path, "승인 문서")
    signature_bytes, _sig_path = _read(signature_path, "서명 파일")
    allowed_signers_bytes, _signers_path = _read(allowed_signers_path, "allowed_signers")

    # ── workflow run 시작 시각 ────────────────────────────────────────
    run = reader.object(f"repos/{run_repository}/actions/runs/{run_id}", "workflow run")
    run_started = _to_utc_second(run.get("run_started_at") if run is not None else None)
    if run_started is None:
        if run is not None:
            reader.fail(
                REMOTE_FACT_MALFORMED, "workflow run 시작 시각을 읽지 못했다",
                expected=f"runs/{run_id}.run_started_at", observed="없음",
            )
        run_started = ""

    # 승인자 login 은 승인 ★문서★ 에서 온다. 워크플로 입력으로 받지 않으므로
    # 문서를 읽은 뒤 read_account_id() 로 따로 조회한다(여기서는 미확정).
    approver_id = None

    # ── 후보 PR 좌표 ──────────────────────────────────────────────────
    head_sha, head_tree, base_sha = read_candidate_head(
        transport=transport, repository=candidate_repository, pr_number=pr_number
    )
    if head_sha is None or head_tree is None or base_sha is None:
        reader.fail(
            REMOTE_FACT_UNAVAILABLE, "후보 PR 좌표를 원격에서 읽지 못했다",
            expected=f"pulls/{pr_number} 의 head sha·tree·base sha",
            observed=f"head={head_sha} tree={head_tree} base={base_sha}",
        )

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
    observation = RemoteObservation(
        facts=facts,
        protected_ref_head=protected_ref_head,
        observed_repository=observed_repository,
        observed_protected_ref=observed_protected_ref,
        observed_document_path=observed_document_path,
        candidate_head_sha=head_sha or "",
        candidate_head_tree=head_tree or "",
        candidate_base_sha=base_sha or "",
    )
    return observation, tuple(reader.errors)


__all__ = [
    "REMOTE_FACT_FORBIDDEN",
    "REMOTE_FACT_MALFORMED",
    "REMOTE_FACT_NOT_FOUND",
    "REMOTE_FACT_RATE_LIMITED",
    "REMOTE_FACT_UNAVAILABLE",
    "RemoteFactError",
    "RemoteObservation",
    "Transport",
    "TransportResult",
    "classify",
    "collect_remote_facts",
    "gh_transport",
    "is_ancestor",
    "read_account_id",
    "read_candidate_head",
]
