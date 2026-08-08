"""Create a non-circular candidate payload manifest before artifact upload."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import tempfile
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Callable, Mapping, Sequence

from .strict_receipt import OID_RE, StrictReceiptError, canonical_json_bytes, validate_path


SCHEMA_VERSION = "butler.ac25.payload-manifest.v1"
API_VERSION = "2026-03-10"
ARTIFACT_JOB_ID_UNRESOLVED = "ARTIFACT_JOB_ID_UNRESOLVED"
ARTIFACT_PROVENANCE_AMBIGUOUS = "ARTIFACT_PROVENANCE_AMBIGUOUS"
_LOGICAL_RE = re.compile(r"\A[a-z0-9][a-z0-9-]{0,62}\Z")


class CandidateArtifactError(Exception):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def resolve_exact_job_id(
    pages: Sequence[Mapping], *, expected_job_name: str, expected_head_sha: str,
) -> int:
    if OID_RE.fullmatch(expected_head_sha or "") is None or not expected_job_name:
        raise CandidateArtifactError(ARTIFACT_JOB_ID_UNRESOLVED)
    matches = []
    for page in pages:
        jobs = page.get("jobs") if isinstance(page, Mapping) else None
        if not isinstance(jobs, list):
            raise CandidateArtifactError(ARTIFACT_JOB_ID_UNRESOLVED)
        matches.extend(
            item for item in jobs
            if isinstance(item, Mapping)
            and item.get("name") == expected_job_name
            and item.get("head_sha") == expected_head_sha
        )
    if len(matches) != 1:
        raise CandidateArtifactError(ARTIFACT_JOB_ID_UNRESOLVED)
    value = matches[0].get("id")
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise CandidateArtifactError(ARTIFACT_JOB_ID_UNRESOLVED)
    return value


def build_payload_manifest(
    *, logical_id: str, repository_id: int, head_sha: str, run_id: int,
    run_attempt: int, job_id: int, job_name: str,
    files: Sequence[tuple[str, bytes]],
) -> bytes:
    if (
        _LOGICAL_RE.fullmatch(logical_id or "") is None
        or not isinstance(repository_id, int) or isinstance(repository_id, bool) or repository_id <= 0
        or OID_RE.fullmatch(head_sha or "") is None
        or any(not isinstance(value, int) or isinstance(value, bool) or value <= 0 for value in (run_id, run_attempt, job_id))
        or not job_name or not files
    ):
        raise CandidateArtifactError(ARTIFACT_PROVENANCE_AMBIGUOUS)
    paths = []
    entries = []
    for path, raw in files:
        validate_path(path)
        if path == "payload-manifest.json" or path in paths or not isinstance(raw, bytes):
            raise CandidateArtifactError(ARTIFACT_PROVENANCE_AMBIGUOUS)
        paths.append(path)
        entries.append({
            "path": path,
            "sha256": hashlib.sha256(raw).hexdigest(),
            "byte_count": len(raw),
        })
    return canonical_json_bytes({
        "schema_version": SCHEMA_VERSION,
        "logical_id": logical_id,
        "repository_id": repository_id,
        "head_sha": head_sha,
        "run_id": run_id,
        "run_attempt": run_attempt,
        "job_id": job_id,
        "job_name": job_name,
        "files": entries,
    })


def artifact_name(logical_id: str, run_id: int, run_attempt: int, job_id: int, head_sha: str) -> str:
    return f"{logical_id}-{run_id}-{run_attempt}-{job_id}-{head_sha}"


def _request_json(url: str, token: str) -> tuple[Mapping, str | None]:
    request = urllib.request.Request(url, headers={
        "Accept": "application/vnd.github+json",
        "Authorization": f"Bearer {token}",
        "X-GitHub-Api-Version": API_VERSION,
        "User-Agent": "butler-ac25-candidate-v4.4",
    })
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            raw = response.read()
            link = response.headers.get("Link")
    except (OSError, urllib.error.HTTPError, urllib.error.URLError) as exc:
        raise CandidateArtifactError(ARTIFACT_JOB_ID_UNRESOLVED) from exc
    try:
        body = json.loads(raw.decode("utf-8", "strict"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise CandidateArtifactError(ARTIFACT_JOB_ID_UNRESOLVED) from exc
    if not isinstance(body, Mapping):
        raise CandidateArtifactError(ARTIFACT_JOB_ID_UNRESOLVED)
    return body, link


def _collect_pages(url: str, token: str, requester: Callable = _request_json) -> list[Mapping]:
    pages = []
    seen: set[str] = set()
    while url:
        parsed = urllib.parse.urlparse(url)
        if parsed.scheme != "https" or parsed.netloc != "api.github.com":
            raise CandidateArtifactError(ARTIFACT_JOB_ID_UNRESOLVED)
        if url in seen or len(pages) >= 100:
            raise CandidateArtifactError(ARTIFACT_JOB_ID_UNRESOLVED)
        seen.add(url)
        body, link = requester(url, token)
        pages.append(body)
        next_url = None
        if link:
            for segment in link.split(","):
                match = re.fullmatch(r'\s*<([^>]+)>;\s*rel="([^"]+)"\s*', segment)
                if match is None:
                    raise CandidateArtifactError(ARTIFACT_JOB_ID_UNRESOLVED)
                if match.group(2) == "next":
                    next_url = match.group(1)
        url = next_url or ""
    return pages


def _positive_env(name: str) -> int:
    value = os.environ.get(name, "")
    if not value.isascii() or not value.isdecimal() or int(value) <= 0:
        raise CandidateArtifactError(ARTIFACT_JOB_ID_UNRESOLVED)
    return int(value)


def _atomic_create(path: Path, raw: bytes) -> None:
    if not path.is_absolute() or not path.parent.is_dir() or path.exists():
        raise CandidateArtifactError(ARTIFACT_PROVENANCE_AMBIGUOUS)
    fd, temporary = tempfile.mkstemp(prefix=".payload.", dir=str(path.parent))
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "wb", closefd=True) as handle:
            handle.write(raw)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        directory_fd = os.open(path.parent, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    except BaseException:
        try:
            os.unlink(temporary)
        except OSError:
            pass
        raise


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--logical-id", required=True)
    parser.add_argument("--job-name", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--file", action="append", default=[], metavar="ARCHIVE_PATH=SOURCE_PATH")
    args = parser.parse_args(argv)
    try:
        repository = os.environ["GITHUB_REPOSITORY"]
        token = os.environ["GITHUB_TOKEN"]
        head_sha = os.environ["AC25_HEAD_SHA"]
        run_id = _positive_env("GITHUB_RUN_ID")
        attempt = _positive_env("GITHUB_RUN_ATTEMPT")
        repository_id = _positive_env("GITHUB_REPOSITORY_ID")
        url = f"https://api.github.com/repos/{repository}/actions/runs/{run_id}/attempts/{attempt}/jobs?per_page=100&page=1"
        job_id = resolve_exact_job_id(
            _collect_pages(url, token), expected_job_name=args.job_name,
            expected_head_sha=head_sha,
        )
        files = []
        for specification in args.file:
            archive_path, separator, source_path = specification.partition("=")
            if not separator:
                raise CandidateArtifactError(ARTIFACT_PROVENANCE_AMBIGUOUS)
            files.append((archive_path, Path(source_path).read_bytes()))
        manifest = build_payload_manifest(
            logical_id=args.logical_id, repository_id=repository_id,
            head_sha=head_sha, run_id=run_id, run_attempt=attempt,
            job_id=job_id, job_name=args.job_name, files=files,
        )
        output = Path(args.output)
        _atomic_create(output, manifest)
        github_output = Path(os.environ["GITHUB_OUTPUT"])
        with github_output.open("a", encoding="utf-8", newline="\n") as handle:
            handle.write(f"job_id={job_id}\n")
            handle.write(f"artifact_name={artifact_name(args.logical_id, run_id, attempt, job_id, head_sha)}\n")
            handle.write(f"payload_manifest_sha256={hashlib.sha256(manifest).hexdigest()}\n")
        return 0
    except (CandidateArtifactError, StrictReceiptError, KeyError, OSError) as exc:
        code = exc.code if isinstance(exc, CandidateArtifactError) else ARTIFACT_JOB_ID_UNRESOLVED
        print(f"ERROR_CODE={code}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "SCHEMA_VERSION", "ARTIFACT_JOB_ID_UNRESOLVED", "ARTIFACT_PROVENANCE_AMBIGUOUS",
    "CandidateArtifactError", "resolve_exact_job_id", "build_payload_manifest", "artifact_name",
]
