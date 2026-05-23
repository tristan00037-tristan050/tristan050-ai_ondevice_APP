from __future__ import annotations

import logging
import socket
import urllib.request

import pytest

from butler_pc_core.observability.egress_monitor_real import EgressMonitorReal


def test_no_external_calls_pass():
    original = socket.socket.connect
    with EgressMonitorReal() as monitor:
        assert monitor._is_local_only("127.0.0.1") is True
        assert monitor._is_local_only("localhost") is True
        assert monitor._is_local_only("::1") is True
        assert monitor._is_local_only("/tmp/app.sock") is True
        report = monitor.report()
        assert report["verdict"] == "PASS"
        assert report["violations"] == []
    assert socket.socket.connect is original


def test_socket_connect_detected():
    original = socket.socket.connect
    with EgressMonitorReal() as monitor:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            with pytest.raises(PermissionError):
                sock.connect(("8.8.8.8", 53))
        finally:
            sock.close()
        report = monitor.report()
        assert report["verdict"] == "FAIL"
        assert report["violations"][0]["kind"] == "socket_connect"
        assert "8.8.8.8" not in str(report)
    assert socket.socket.connect is original


def test_urllib_request_detected():
    with EgressMonitorReal() as monitor:
        with pytest.raises(PermissionError):
            urllib.request.urlopen("https://example.com")
        report = monitor.report()
        assert report["verdict"] == "FAIL"
        assert report["violations"][0]["kind"] == "urllib"
        assert "example.com" not in str(report)


def test_raw_text_log_detected():
    private_text = "가" * 101
    with EgressMonitorReal() as monitor:
        logging.getLogger("egress-test").warning(private_text)
        report = monitor.report()
        assert report["raw_text_logged"] is True
        assert report["violations"][0]["kind"] == "logging"
        assert private_text not in str(report)
        assert len(report["violations"][0]["target_digest16"]) == 16


def test_telemetry_detected():
    with EgressMonitorReal() as monitor:
        monitor.record_telemetry_attempt("telemetry.example.invalid")
        report = monitor.report()
        assert report["telemetry_enabled"] is True
        assert report["verdict"] == "FAIL"
        assert "telemetry.example.invalid" not in str(report)


def test_verdict_fail_on_violation_and_duplicate_start():
    monitor = EgressMonitorReal()
    with monitor:
        with pytest.raises(RuntimeError):
            monitor.start()
        with pytest.raises(PermissionError):
            urllib.request.urlopen("http://public.example.invalid")
        assert monitor.report()["verdict"] == "FAIL"
    assert monitor._originals == {}
