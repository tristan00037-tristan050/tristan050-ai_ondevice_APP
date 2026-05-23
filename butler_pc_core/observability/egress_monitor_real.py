from __future__ import annotations

import hashlib
import logging
import re
import socket
import urllib.request
from datetime import datetime, timezone
from typing import Any, Optional


class EgressMonitorReal:
    def __init__(self) -> None:
        self._started = False
        self._originals: dict[str, Any] = {}
        self._restore_errors: list[tuple[str, str]] = []
        self.violations: list[dict[str, str]] = []
        self.patched_targets: list[str] = []
        self.skipped_targets: list[str] = []
        self.raw_text_logged = False
        self.telemetry_enabled = False

    def __enter__(self) -> "EgressMonitorReal":
        if self._started:
            raise RuntimeError("duplicate start is forbidden")
        self.start()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        try:
            self.stop()
        finally:
            self._started = False

    def _digest16(self, value: str) -> str:
        return hashlib.sha256(value.encode("utf-8")).hexdigest()[:16]

    def _timestamp(self) -> str:
        return datetime.now(timezone.utc).isoformat()

    def _record_violation(self, kind: str, target: str) -> None:
        self.violations.append({
            "kind": kind,
            "target_digest16": self._digest16(target),
            "timestamp": self._timestamp(),
        })

    def _is_local_only(self, host: str) -> bool:
        if host in ("127.0.0.1", "::1", "localhost"):
            return True
        if host.startswith("/"):
            return True
        return False

    def _detect_raw_text(self, log_text: str) -> Optional[str]:
        if re.search(r"\d{6}-\d{7}", log_text):
            return "rrn_pattern"
        if re.search(r"\d{4}-\d{4}-\d{4}-\d{4}", log_text):
            return "card_pattern"
        if re.search(r"\d{3}-\d{2}-\d{6}|\d{3}-\d{6}-\d{2}-\d{3}", log_text):
            return "account_pattern"
        if re.search(r"01\d-\d{3,4}-\d{4}", log_text):
            return "phone_pattern"
        if re.search(r"[가-힣a-zA-Z]{100,}", log_text):
            return "long_text"
        if re.search(r"[A-Za-z0-9+/]{200,}={0,2}", log_text):
            return "base64_long"
        return None

    def _record_raw_text(self, log_text: str, reason: str) -> dict[str, Any]:
        digest = self._digest16(log_text)
        self.raw_text_logged = True
        self.violations.append({
            "kind": "logging",
            "target_digest16": digest,
            "timestamp": self._timestamp(),
        })
        return {"raw_text_logged": True, "raw_text_reason": reason, "raw_text_digest16": digest}

    def _patch_optional_libs(self) -> tuple[list[str], list[str]]:
        patched: list[str] = []
        skipped: list[str] = []
        try:
            import requests  # type: ignore
            original = requests.sessions.Session.request
            self._originals["requests.sessions.Session.request"] = original

            def request_patch(session, method, url, *args, **kwargs):
                host = str(url).split("//", 1)[-1].split("/", 1)[0].split(":", 1)[0]
                if not self._is_local_only(host):
                    self._record_violation("requests", str(url))
                    raise PermissionError("external requests call blocked")
                return original(session, method, url, *args, **kwargs)

            requests.sessions.Session.request = request_patch
            patched.append("requests")
        except ImportError:
            skipped.append("requests")

        try:
            import aiohttp  # type: ignore  # noqa: F401
            patched.append("aiohttp")
        except ImportError:
            skipped.append("aiohttp")

        try:
            import httpx  # type: ignore
            original_httpx = httpx.Client.request
            self._originals["httpx.Client.request"] = original_httpx

            def httpx_patch(client, method, url, *args, **kwargs):
                host = str(url).split("//", 1)[-1].split("/", 1)[0].split(":", 1)[0]
                if not self._is_local_only(host):
                    self._record_violation("httpx", str(url))
                    raise PermissionError("external httpx call blocked")
                return original_httpx(client, method, url, *args, **kwargs)

            httpx.Client.request = httpx_patch
            patched.append("httpx")
        except ImportError:
            skipped.append("httpx")

        return patched, skipped

    def start(self) -> None:
        if self._started:
            raise RuntimeError("duplicate start is forbidden")
        self._started = True
        self._originals["socket.socket.connect"] = socket.socket.connect
        self._originals["urllib.request.urlopen"] = urllib.request.urlopen
        self._originals["logging.Logger._log"] = logging.Logger._log

        original_connect = socket.socket.connect
        original_urlopen = urllib.request.urlopen
        original_log = logging.Logger._log

        def connect_patch(sock, address):
            host = address if isinstance(address, str) else str(address[0])
            if not self._is_local_only(host):
                self._record_violation("socket_connect", host)
                raise PermissionError("external socket connect blocked")
            return original_connect(sock, address)

        def urlopen_patch(url, *args, **kwargs):
            target = getattr(url, "full_url", url)
            text = str(target)
            host = text.split("//", 1)[-1].split("/", 1)[0].split(":", 1)[0]
            if not self._is_local_only(host):
                self._record_violation("urllib", text)
                raise PermissionError("external urllib call blocked")
            return original_urlopen(url, *args, **kwargs)

        def log_patch(logger, level, msg, args, exc_info=None, extra=None, stack_info=False, stacklevel=1):
            text = str(msg)
            reason = self._detect_raw_text(text)
            if reason:
                self._record_raw_text(text, reason)
            return original_log(logger, level, msg, args, exc_info, extra, stack_info, stacklevel)

        socket.socket.connect = connect_patch
        urllib.request.urlopen = urlopen_patch
        logging.Logger._log = log_patch
        self.patched_targets.extend(["socket", "urllib", "logging"])
        patched, skipped = self._patch_optional_libs()
        self.patched_targets.extend(patched)
        self.skipped_targets.extend(skipped)

    def stop(self) -> None:
        restore_map = {
            "socket.socket.connect": (socket.socket, "connect"),
            "urllib.request.urlopen": (urllib.request, "urlopen"),
            "logging.Logger._log": (logging.Logger, "_log"),
        }
        for name, original in list(self._originals.items()):
            try:
                if name in restore_map:
                    obj, attr = restore_map[name]
                    setattr(obj, attr, original)
                elif name == "requests.sessions.Session.request":
                    import requests  # type: ignore
                    requests.sessions.Session.request = original
                elif name == "httpx.Client.request":
                    import httpx  # type: ignore
                    httpx.Client.request = original
            except Exception as exc:
                self._restore_errors.append((name, str(exc)))
        self._originals.clear()

    def record_telemetry_attempt(self, target: str) -> None:
        self.telemetry_enabled = True
        self._record_violation("telemetry", target)

    def report(self) -> dict[str, Any]:
        first_ts = self.violations[0]["timestamp"] if self.violations else None
        return {
            "schema_version": "egress_report.v2",
            "mode": "local_only",
            "raw_file_sent_external": False,
            "raw_text_logged": self.raw_text_logged,
            "telemetry_enabled": self.telemetry_enabled,
            "external_calls_count": len(self.violations),
            "external_calls_blocked": len(self.violations),
            "first_violation_timestamp": first_ts,
            "verdict": "FAIL" if self.violations else "PASS",
            "patched_targets": self.patched_targets,
            "skipped_targets": self.skipped_targets,
            "violations": list(self.violations),
        }
