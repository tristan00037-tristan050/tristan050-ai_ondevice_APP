from __future__ import annotations

import json
import os
import re
import selectors
import signal
import subprocess
import time
from pathlib import Path
from typing import Any

from .artifact_scanner import scan_bytes_all_encodings
from .canonical import canonical_sha256, sha256_bytes, sha256_file
from .errors import ExitCode, FailClass, GateError

EVENT_ORDER = (
    "READY_PRELOAD", "MODEL_LOADED", "INFERENCE_START", "FIRST_CHUNK",
    "INFERENCE_END", "RESULT", "CLOSED",
)
EVENT_KEYS = {
    "schema_version", "run_id", "worker_id", "seq", "event_type", "monotonic_ns",
    "wall_time_utc", "challenge_sha256", "payload_sha256", "safe_payload",
}
PAYLOAD_KEYS = {
    "READY_PRELOAD": {"worker_pid", "parent_pid", "executable_sha256", "provenance_sha256"},
    "MODEL_LOADED": {"model_manifest_sha256", "runtime_config_sha256", "loader_fd_set_sha256"},
    "INFERENCE_START": {"fixture_id", "request_sha256"},
    "FIRST_CHUNK": {"token_count", "output_prefix_sha256"},
    "INFERENCE_END": {"output_token_count", "output_stream_sha256"},
    "RESULT": {"status", "final_gate", "fail_class", "verdict_sha256"},
    "CLOSED": {"descendant_count"},
}
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_RFC3339 = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,9})?Z$")
MAX_LINE_BYTES = 64 * 1024
MAX_EVENTS = 128
MAX_STREAM_BYTES = 4 * 1024 * 1024


def make_challenge(
    *, nonce_hex: str, executable_sha256: str, model_manifest_sha256: str,
    runtime_config_sha256: str, request_sha256: str,
) -> str:
    if not re.fullmatch(r"[0-9a-f]{64}", nonce_hex):
        _block("NONCE_256_BIT")
    values = {
        "nonce_hex": nonce_hex,
        "executable_sha256": executable_sha256,
        "model_manifest_sha256": model_manifest_sha256,
        "runtime_config_sha256": runtime_config_sha256,
        "request_sha256": request_sha256,
    }
    if any(not _SHA256.fullmatch(value) for key, value in values.items() if key != "nonce_hex"):
        _block("CHALLENGE_INPUT_DIGEST")
    return canonical_sha256(values)


def verify_worker_stream(
    stdout: bytes,
    stderr: bytes,
    returncode: int,
    *,
    expected: dict[str, Any],
    parent_event_arrival_ns: list[int],
    parent_pipe_write_complete_ns: int,
    parent_eof_ns: int,
) -> dict[str, Any]:
    if len(stdout) > MAX_STREAM_BYTES or len(stderr) > MAX_STREAM_BYTES:
        _block("STREAM_LIMIT")
    if stdout and not stdout.endswith(b"\n"):
        _block("STDOUT_PARTIAL_TAIL")
    if stderr and not stderr.endswith(b"\n"):
        _block("STDERR_PARTIAL_TAIL", ExitCode.SECURITY)
    if scan_bytes_all_encodings(stderr, file_sha256=sha256_bytes(stderr)):
        raise GateError(FailClass.SECURITY_PRIVACY, "STDERR_SENSITIVE", exit_code=ExitCode.SECURITY)
    lines = stdout.splitlines()
    if len(lines) > MAX_EVENTS or len(lines) != len(EVENT_ORDER):
        _block("EVENT_CARDINALITY")
    if len(parent_event_arrival_ns) != len(lines):
        _block("PARENT_ARRIVAL_CARDINALITY")
    if any(type(value) is not int or value <= 0 for value in parent_event_arrival_ns):
        _block("PARENT_ARRIVAL_CLOCK")
    if parent_event_arrival_ns != sorted(set(parent_event_arrival_ns)):
        _block("PARENT_ARRIVAL_ORDER")
    if not 0 < parent_pipe_write_complete_ns <= parent_event_arrival_ns[0] < parent_eof_ns:
        _block("PARENT_OBSERVATION_INTERVAL")
    events: list[dict[str, Any]] = []
    for line in lines:
        if len(line) > MAX_LINE_BYTES:
            _block("EVENT_LINE_LIMIT")
        try:
            event = json.loads(line, object_pairs_hook=_unique_object, parse_constant=_reject_number, parse_float=_reject_number)
        except (UnicodeError, json.JSONDecodeError, ValueError):
            raise GateError(FailClass.PROTOCOL, "EVENT_JSON", exit_code=ExitCode.SCHEMA) from None
        events.append(event)
    if tuple(event.get("event_type") for event in events) != EVENT_ORDER:
        _block("EVENT_ORDER")
    for index, event in enumerate(events):
        _verify_event(event, index=index, previous=events[index - 1] if index else None, expected=expected)
        if event["monotonic_ns"] > parent_event_arrival_ns[index]:
            _block("WORKER_CLOCK_AFTER_PARENT_ARRIVAL")
    _verify_bindings(events, expected)
    if returncode != 0 or events[-1]["safe_payload"]["descendant_count"] != 0:
        _block("WORKER_CLOSE_OR_DESCENDANT")
    result = events[-2]["safe_payload"]
    if (result["status"] == "PASS") != (result["final_gate"] == "ALLOW"):
        _block("RESULT_TERMINAL_BINDING")
    worker_ttft = events[3]["monotonic_ns"] - events[2]["monotonic_ns"]
    parent_ttft = parent_event_arrival_ns[3] - parent_event_arrival_ns[2]
    if worker_ttft <= 0 or parent_ttft <= 0:
        _block("TTFT_NONPOSITIVE")
    return {
        "schema_version": "butler.model-tier-b.worker-stream-index.v2.8",
        "event_count": len(events),
        "stdout_sha256": sha256_bytes(stdout),
        "stdout_bytes": len(stdout),
        "stderr_sha256": sha256_bytes(stderr),
        "stderr_bytes": len(stderr),
        "returncode": returncode,
        "worker_ttft_ns": worker_ttft,
        "parent_observed_ttft_ns": parent_ttft,
        "events_digest_sha256": canonical_sha256(events),
        "challenge_sha256": expected["challenge_sha256"],
    }


def _verify_event(event: object, *, index: int, previous: dict[str, Any] | None, expected: dict[str, Any]) -> None:
    if not isinstance(event, dict) or set(event) != EVENT_KEYS:
        raise GateError(FailClass.PROTOCOL, "EVENT_KEYS", exit_code=ExitCode.SCHEMA)
    if event["schema_version"] != "butler.model-tier-b.worker-event.v2.8":
        raise GateError(FailClass.PROTOCOL, "EVENT_VERSION", exit_code=ExitCode.SCHEMA)
    if event["seq"] != index or event["event_type"] != EVENT_ORDER[index]:
        _block("EVENT_SEQ_OR_TYPE")
    if event["challenge_sha256"] != expected.get("challenge_sha256"):
        _block("CHALLENGE_REPLAY_OR_MISMATCH")
    clock = event["monotonic_ns"]
    if type(clock) is not int or clock <= 0 or (previous is not None and clock <= previous["monotonic_ns"]):
        _block("EVENT_CLOCK")
    if not isinstance(event["wall_time_utc"], str) or not _RFC3339.fullmatch(event["wall_time_utc"]):
        raise GateError(FailClass.PROTOCOL, "EVENT_WALL_TIME", exit_code=ExitCode.SCHEMA)
    payload = event["safe_payload"]
    if not isinstance(payload, dict) or set(payload) != PAYLOAD_KEYS[event["event_type"]]:
        raise GateError(FailClass.PROTOCOL, "EVENT_PAYLOAD_KEYS", exit_code=ExitCode.SCHEMA)
    if canonical_sha256(payload) != event["payload_sha256"]:
        raise GateError(FailClass.PROTOCOL, "EVENT_PAYLOAD_DIGEST", exit_code=ExitCode.DIGEST)
    if event["event_type"] == "FIRST_CHUNK" and (type(payload["token_count"]) is not int or payload["token_count"] < 1):
        _block("FIRST_CHUNK_EMPTY")


def _verify_bindings(events: list[dict[str, Any]], expected: dict[str, Any]) -> None:
    required = {
        "challenge_sha256", "worker_pid", "parent_pid", "executable_sha256", "provenance_sha256",
        "model_manifest_sha256", "runtime_config_sha256", "request_sha256", "output_token_count",
    }
    if set(expected) != required:
        _block("EXPECTED_PROCESS_KEYS")
    ready = events[0]["safe_payload"]
    loaded = events[1]["safe_payload"]
    start = events[2]["safe_payload"]
    end = events[4]["safe_payload"]
    comparisons = {
        "worker_pid": ready["worker_pid"],
        "parent_pid": ready["parent_pid"],
        "executable_sha256": ready["executable_sha256"],
        "provenance_sha256": ready["provenance_sha256"],
        "model_manifest_sha256": loaded["model_manifest_sha256"],
        "runtime_config_sha256": loaded["runtime_config_sha256"],
        "request_sha256": start["request_sha256"],
        "output_token_count": end["output_token_count"],
    }
    for key, observed in comparisons.items():
        if observed != expected[key]:
            _block(f"BINDING_{key.upper()}")


def run_worker_bounded(
    command: list[str], *, deadline_seconds: int, cwd: Path,
    executable_sha256: str, max_stream_bytes: int = MAX_STREAM_BYTES,
) -> tuple[bytes, bytes, int, list[int], int, int]:
    if not command or deadline_seconds <= 0 or max_stream_bytes <= 0:
        _block("WORKER_COMMAND")
    executable = Path(command[0]).resolve(strict=True)
    if sha256_file(executable) != executable_sha256:
        raise GateError(FailClass.IDENTITY, "WORKER_EXECUTABLE_DIGEST", exit_code=ExitCode.DIGEST)
    process = subprocess.Popen(
        command,
        cwd=cwd,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env={"PATH": "", "PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8"},
        start_new_session=True,
        bufsize=0,
    )
    assert process.stdout is not None and process.stderr is not None
    selector = selectors.DefaultSelector()
    selector.register(process.stdout, selectors.EVENT_READ, "stdout")
    selector.register(process.stderr, selectors.EVENT_READ, "stderr")
    buffers = {"stdout": bytearray(), "stderr": bytearray()}
    arrivals: list[int] = []
    stdout_line_count = 0
    started = time.monotonic_ns()
    deadline_ns = started + deadline_seconds * 1_000_000_000
    try:
        while selector.get_map():
            if time.monotonic_ns() >= deadline_ns:
                _terminate_group(process)
                _block("WORKER_TIMEOUT")
            for key, _ in selector.select(timeout=0.05):
                chunk = os.read(key.fileobj.fileno(), 65536)
                if not chunk:
                    selector.unregister(key.fileobj)
                    continue
                target = buffers[key.data]
                target.extend(chunk)
                if len(target) > max_stream_bytes:
                    _terminate_group(process)
                    _block("STREAM_LIMIT")
                if key.data == "stdout":
                    new_count = target.count(b"\n")
                    arrivals.extend([time.monotonic_ns()] * (new_count - stdout_line_count))
                    stdout_line_count = new_count
        returncode = process.wait(timeout=1)
    except Exception:
        if process.poll() is None:
            _terminate_group(process)
        raise
    eof_ns = time.monotonic_ns()
    if _process_group_members(process.pid):
        _block("DESCENDANT_PROCESS_LEAK")
    return bytes(buffers["stdout"]), bytes(buffers["stderr"]), returncode, arrivals, started, eof_ns


def _terminate_group(process: subprocess.Popen[bytes]) -> None:
    try:
        os.killpg(process.pid, signal.SIGTERM)
    except ProcessLookupError:
        return
    try:
        process.wait(timeout=2)
    except subprocess.TimeoutExpired:
        os.killpg(process.pid, signal.SIGKILL)
        process.wait(timeout=2)


def _process_group_members(pgid: int) -> list[int]:
    try:
        completed = subprocess.run(
            ["ps", "-o", "pid=", "-g", str(pgid)],
            stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=2, check=False,
            env={"PATH": "/usr/bin:/bin", "LANG": "C"},
        )
    except (OSError, subprocess.TimeoutExpired):
        _block("PROCESS_GROUP_INSPECTION")
    return [int(item) for item in completed.stdout.split() if item.isdigit()]


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate key")
        result[key] = value
    return result


def _reject_number(_: str) -> None:
    raise ValueError("unsupported number")


def _block(detail: str, exit_code: ExitCode = ExitCode.PROTOCOL) -> None:
    raise GateError(FailClass.PROTOCOL, detail, exit_code=exit_code)
