#!/usr/bin/env python3
"""Replay fixed historical verifier bypasses with protected code only."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import tempfile
import zipfile
from pathlib import Path
from typing import Any


class HistoricalError(RuntimeError):
    pass


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise HistoricalError("PROTECTED_MODULE_LOAD_FAILED")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class _MismatchApi:
    def __init__(self, repository: str, head: str, tree: str) -> None:
        self.repository = repository
        self.head = head
        self.tree = tree

    def json(self, path: str):
        if path.endswith("/pulls/886"):
            return {"number": 886, "head": {"sha": "f" * 40}}
        if path.endswith("/actions/workflows/7"):
            return {
                "id": 7,
                "name": "firstscreen-v2-5-product-gate",
                "path": ".github/workflows/firstscreen-v2-5.yml",
                "state": "active",
            }
        if path.endswith(f"/git/commits/{self.head}"):
            return {"sha": self.head, "tree": {"sha": self.tree}}
        raise KeyError(path)

    def download(self, path: str, output: Path) -> str:
        raise AssertionError("download must not be reached")


def _rejected(callback) -> bool:
    try:
        callback()
    except Exception:
        return True
    return False


def replay(operator: str, *, artifact, run, root: Path) -> bool:
    if operator == "merge_ref_as_head":
        repository = "tristan00037-tristan050/tristan050-ai_ondevice_APP"
        head = "a" * 40
        tree = "b" * 40
        event = {
            "repository": {"full_name": repository},
            "workflow_run": {
                "id": 123,
                "run_attempt": 1,
                "workflow_id": 7,
                "name": "firstscreen-v2-5-product-gate",
                "event": "pull_request",
                "conclusion": "success",
                "head_sha": head,
                "head_repository": {"full_name": repository},
                "pull_requests": [{"number": 886}],
            },
        }
        return _rejected(
            lambda: run.resolve_run(
                event,
                _MismatchApi(repository, head, tree),
                repository=repository,
                workflow_name="firstscreen-v2-5-product-gate",
                workflow_path=".github/workflows/firstscreen-v2-5.yml",
                artifact_prefix="firstscreen-v9-evidence-",
                artifact_output=root / "artifact.zip",
                trusted_head="c" * 40,
                trusted_tree="d" * 40,
                trusted_workflow_ref="trusted",
            )
        )
    if operator == "symlink_report":
        target = root / "target"
        target.write_text("x", encoding="utf-8")
        link = root / "report"
        link.symlink_to(target)
        return _rejected(
            lambda: artifact._require_regular(link, max_bytes=1024)
        )
    if operator == "oversized_report":
        target = root / "oversized"
        with target.open("wb") as stream:
            stream.truncate(2048)
        return _rejected(
            lambda: artifact._require_regular(target, max_bytes=1024)
        )
    if operator == "archive_namespace_attack":
        archive_path = root / "attack.zip"
        with zipfile.ZipFile(archive_path, "w") as archive_file:
            archive_file.writestr("../escape", b"x")

        def inspect() -> None:
            with archive_path.open("rb") as stream:
                archive_file, _ = artifact._preflight(stream)
                archive_file.close()

        return _rejected(inspect)
    raise HistoricalError("UNKNOWN_HISTORICAL_OPERATOR")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository-root", type=Path, required=True)
    parser.add_argument("--corpus", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    root = args.repository_root.resolve()
    artifact = _load(
        "trusted_firstscreen_artifact",
        root / "scripts/ci/trusted_firstscreen_artifact.py",
    )
    run = _load(
        "trusted_firstscreen_run",
        root / "scripts/ci/trusted_firstscreen_run.py",
    )
    try:
        corpus = artifact._strict_json(args.corpus, max_bytes=64 * 1024)
        cases = corpus.get("cases")
        if corpus.get("schema_version") != 1 or not isinstance(cases, list):
            raise HistoricalError("HISTORICAL_CORPUS_INVALID")
        selected = [
            item for item in cases
            if isinstance(item, dict) and item.get("runner") == "python"
        ]
        if not selected:
            raise HistoricalError("HISTORICAL_CORPUS_EMPTY")
        ids: set[str] = set()
        with tempfile.TemporaryDirectory(prefix="butler-trusted-history-") as temp:
            temp_root = Path(temp)
            for index, item in enumerate(selected):
                identifier = item.get("id")
                operator = item.get("operator")
                if (
                    not isinstance(identifier, str)
                    or identifier in ids
                    or not isinstance(operator, str)
                ):
                    raise HistoricalError("HISTORICAL_CASE_INVALID")
                case_root = temp_root / str(index)
                case_root.mkdir(mode=0o700)
                if not replay(operator, artifact=artifact, run=run, root=case_root):
                    raise HistoricalError("HISTORICAL_ATTACK_ACCEPTED")
                ids.add(identifier)
        result = {
            "schema_version": 1,
            "corpus_sha256": hashlib.sha256(args.corpus.read_bytes()).hexdigest(),
            "python_cases": len(selected),
            "accepted_malicious": 0,
            "unanalysed": 0,
        }
        descriptor = os.open(
            args.output,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_CLOEXEC", 0),
            0o600,
        )
        try:
            payload = (
                json.dumps(result, separators=(",", ":")) + "\n"
            ).encode("utf-8")
            view = memoryview(payload)
            while view:
                written = os.write(descriptor, view)
                if written <= 0:
                    raise HistoricalError("HISTORICAL_OUTPUT_WRITE_FAILED")
                view = view[written:]
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
    except (HistoricalError, OSError, ValueError) as exc:
        code = str(exc) if str(exc).isupper() else "HISTORICAL_REPLAY_FAILED"
        print("TRUSTED_HISTORICAL_REPLAY_OK=0")
        print(f"ERROR_CODE={code}")
        return 1
    print("TRUSTED_HISTORICAL_REPLAY_OK=1")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
