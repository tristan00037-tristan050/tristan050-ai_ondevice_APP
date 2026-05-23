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


def test_log_args_sensitive_value_detected():
    """
    Codex P1 회귀 방지 — logger.warning("acct=%s", value) 본질 패턴의
    민감 정보 (카드번호)가 args로 전달될 때 raw_text_logged 본질 정확히 기록.
    이전 본질: str(msg)만 검사 → "acct=%s"에는 패턴 0 → 탐지 우회.
    정정 본질: msg % args 포맷팅 후 검사 → 카드번호 패턴 본질 탐지.
    """
    card_number = "1234-5678-9012-3456"  # card_pattern 본질
    with EgressMonitorReal() as monitor:
        logging.getLogger("butler.test.egress.args").warning("acct=%s", card_number)
        report = monitor.report()
    assert report["raw_text_logged"] is True, "args 본질 누출 미탐지"
    assert any(v["kind"] == "logging" for v in report["violations"])
    # PII 보호 본질: 원본 카드번호 본질이 report에 노출 0
    assert card_number not in str(report)


def test_log_args_format_failure_still_scans():
    """
    Codex P1 회귀 방지 — 포맷 실패 본질 (%d에 str) 시에도 args 원본 본질이
    raw 검사 대상이어야 함 (이중 안전).

    Note: pytest LogCaptureHandler 본질이 format 재시도 시 TypeError를 swallow 0
    하므로, 격리된 NullHandler 본질 logger 사용 (production 본질 정합 유지).
    """
    card_number = "1234-5678-9012-3456"  # %d 포맷 실패 본질 + card_pattern
    test_logger = logging.getLogger("butler.test.egress.fmt_fail")
    test_logger.propagate = False
    test_logger.handlers = [logging.NullHandler()]
    with EgressMonitorReal() as monitor:
        # %d에 str 본질 — TypeError 발생 본질
        # 우리 log_patch는 정정 본질 후 detect 본질 성공, 이후 original_log은
        # NullHandler 본질에 도달 → format 시도 0 → TypeError escape 0.
        test_logger.warning("count=%d", card_number)
        report = monitor.report()
    assert report["raw_text_logged"] is True, "포맷 실패 본질 fallback 누출 미탐지"
    assert any(v["kind"] == "logging" for v in report["violations"])


def test_aiohttp_not_reported_as_patched_when_unenforced():
    """
    Codex P2 회귀 방지 — aiohttp가 import 가능 본질이어도 실제 monkey-patch
    미구현 본질이면 patched_targets 본질에 추가 0 (false coverage 차단).
    """
    with EgressMonitorReal() as monitor:
        report = monitor.report()
    assert "aiohttp" not in report["patched_targets"], (
        "aiohttp 본질이 patched_targets에 잘못 포함됨 — false coverage 본질"
    )


def test_aiohttp_importable_emits_warning(recwarn):
    """
    Codex P2 회귀 방지 — aiohttp import 가능 본질일 때 RuntimeWarning 본질
    발생 (운영 알림 — egress 경로 unguarded 명시).
    """
    pytest.importorskip("aiohttp")
    with EgressMonitorReal():
        pass
    matched = [
        w for w in recwarn.list
        if issubclass(w.category, RuntimeWarning) and "aiohttp" in str(w.message)
    ]
    assert matched, f"aiohttp RuntimeWarning 본질 미발생: {[str(w.message) for w in recwarn.list]}"
