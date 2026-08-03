#!/usr/bin/env python3
"""Exercise the protected Helper1 replay store against a real PostgreSQL service."""
from __future__ import annotations

import argparse
import base64
import hashlib
import os
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from butler_pc_core.helper1.replay_store import (
    PostgreSQLReplayStore,
    ReplayReservation,
    ReplayStoreError,
)

KEY_ID = "butler/helper1/protected-replay-probe/v1"
CHILD_TIMEOUT_SECONDS = 30


def _token(material: bytes) -> str:
    return base64.urlsafe_b64encode(material).decode("ascii").rstrip("=")


def _reservation(run_id: str, lane: str, now: int) -> ReplayReservation:
    material = hashlib.sha256(f"{run_id}:{lane}".encode("utf-8")).digest()
    return ReplayReservation(
        policy_sha256=hashlib.sha256(f"helper1:{run_id}:{lane}".encode("utf-8")).hexdigest(),
        key_id=KEY_ID,
        nonce=_token(material),
        expires_at_epoch_s=now + 600,
    )


def _error_code(error: ReplayStoreError) -> str:
    return {
        "REPLAY_STORE_DSN_INVALID": "APPROVAL_REPLAY_STORE_CONFIGURATION_INVALID",
        "REPLAY_STORE_DNS_RESOLUTION_FAILED": "APPROVAL_REPLAY_STORE_DNS_RESOLUTION_FAILED",
        "REPLAY_STORE_ENDPOINT_FORBIDDEN": "APPROVAL_REPLAY_STORE_ENDPOINT_FORBIDDEN",
        "REPLAY_STORE_ROUTING_ENV_FORBIDDEN": "APPROVAL_REPLAY_STORE_ROUTING_ENV_FORBIDDEN",
        "REPLAY_STORE_DRIVER_UNAVAILABLE": "APPROVAL_REPLAY_STORE_DRIVER_UNAVAILABLE",
        "REPLAY_STORE_CONNECTION_FAILED": "APPROVAL_REPLAY_STORE_CONNECTION_FAILED",
        "REPLAY_STORE_SCHEMA_FAILED": "APPROVAL_REPLAY_STORE_SCHEMA_FAILED",
        "REPLAY_RESERVATION_FAILED": "APPROVAL_REPLAY_STORE_RESERVATION_FAILED",
    }.get(str(error), "APPROVAL_REPLAY_STORE_FAILED")


def _child(args: argparse.Namespace) -> int:
    dsn = os.environ.get("HELPER1_APPROVAL_REPLAY_DSN")
    if not dsn:
        print("REPLAY_RESERVATION_OK=0")
        print("ERROR_CODE=APPROVAL_REPLAY_STORE_UNAVAILABLE")
        return 2
    reservation = ReplayReservation(
        policy_sha256=args.policy_sha256,
        key_id=KEY_ID,
        nonce=args.nonce,
        expires_at_epoch_s=args.expires_at,
    )
    try:
        PostgreSQLReplayStore(dsn).reserve_many((reservation,), now_epoch_s=args.now)
    except ReplayStoreError as exc:
        code = str(exc)
        print("REPLAY_RESERVATION_OK=0")
        print(f"ERROR_CODE={code if code == 'EVIDENCE_REPLAY_DETECTED' else _error_code(exc)}")
        return 3 if code == "EVIDENCE_REPLAY_DETECTED" else 2
    print("REPLAY_RESERVATION_OK=1")
    print("ERROR_CODE=NONE")
    return 0


def _child_argv(item: ReplayReservation, now: int) -> list[str]:
    return [
        sys.executable,
        str(__file__),
        "--child",
        "--policy-sha256",
        item.policy_sha256,
        "--nonce",
        item.nonce,
        "--expires-at",
        str(item.expires_at_epoch_s),
        "--now",
        str(now),
    ]


def _run_parent() -> int:
    if not os.environ.get("HELPER1_APPROVAL_REPLAY_DSN"):
        print("HELPER1_POSTGRES_REPLAY_PROBE_OK=0")
        print("ERROR_CODE=APPROVAL_REPLAY_STORE_UNAVAILABLE")
        return 1
    run_id = os.environ.get("HELPER1_REPLAY_PROBE_RUN_ID", "")
    if not run_id or len(run_id) > 128 or any(ord(ch) < 33 or ord(ch) > 126 for ch in run_id):
        print("HELPER1_POSTGRES_REPLAY_PROBE_OK=0")
        print("ERROR_CODE=REPLAY_PROBE_RUN_ID_INVALID")
        return 1
    now = int(time.time())
    sequential = _reservation(run_id, "sequential", now)
    first = subprocess.run(
        _child_argv(sequential, now),
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=CHILD_TIMEOUT_SECONDS,
        check=False,
    )
    second = subprocess.run(
        _child_argv(sequential, now),
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=CHILD_TIMEOUT_SECONDS,
        check=False,
    )
    if first.returncode != 0 or second.returncode != 3:
        print("HELPER1_POSTGRES_REPLAY_PROBE_OK=0")
        print("ERROR_CODE=REPLAY_PROBE_SEQUENTIAL_FAILED")
        return 1

    concurrent = _reservation(run_id, "concurrent", now)
    processes = [
        subprocess.Popen(
            _child_argv(concurrent, now),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        for _ in range(8)
    ]
    return_codes = []
    try:
        for process in processes:
            process.communicate(timeout=CHILD_TIMEOUT_SECONDS)
            return_codes.append(process.returncode)
    except subprocess.TimeoutExpired:
        for process in processes:
            process.kill()
            process.communicate()
        print("HELPER1_POSTGRES_REPLAY_PROBE_OK=0")
        print("ERROR_CODE=REPLAY_PROBE_TIMEOUT")
        return 1
    if return_codes.count(0) != 1 or return_codes.count(3) != len(processes) - 1:
        print("HELPER1_POSTGRES_REPLAY_PROBE_OK=0")
        print("ERROR_CODE=REPLAY_PROBE_CONCURRENCY_FAILED")
        return 1

    print("HELPER1_POSTGRES_REPLAY_PROBE_OK=1")
    print("SEQUENTIAL_REPLAY_BLOCKED=1")
    print("CONCURRENT_SINGLE_WINNER=1")
    print("ERROR_CODE=NONE")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--child", action="store_true")
    parser.add_argument("--policy-sha256")
    parser.add_argument("--nonce")
    parser.add_argument("--expires-at", type=int)
    parser.add_argument("--now", type=int)
    args = parser.parse_args()
    if not args.child:
        return _run_parent()
    if (
        not args.policy_sha256
        or not args.nonce
        or args.expires_at is None
        or args.now is None
    ):
        print("REPLAY_RESERVATION_OK=0")
        print("ERROR_CODE=REPLAY_PROBE_ARGUMENT_INVALID")
        return 2
    return _child(args)


if __name__ == "__main__":
    sys.exit(main())
