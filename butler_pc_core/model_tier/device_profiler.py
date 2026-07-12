from __future__ import annotations

import json
import os
import platform
import re
import subprocess
import threading
import time
from typing import Any, Mapping

from .contracts import (
    DeviceProfile,
    MemoryPressure,
    ProfileValidity,
    ThermalState,
)


NATIVE_TELEMETRY_ENV = "BUTLER_MODEL_TIER_NATIVE_TELEMETRY_JSON"
NATIVE_ALLOWED_KEYS = frozenset(
    {
        "total_memory_bytes",
        "available_memory_bytes",
        "process_rss_bytes",
        "memory_pressure",
        "thermal_state",
        "low_power_mode",
        "battery_percent",
        "metal_available",
        "chip_family",
    }
)
_ALLOWED_COMMANDS = {
    ("/usr/sbin/sysctl", "-n", "hw.memsize"),
    ("/usr/sbin/sysctl", "-n", "machdep.cpu.brand_string"),
    ("/usr/bin/vm_stat",),
}


def _run_allowlisted(command: tuple[str, ...], timeout: float = 1.5) -> str | None:
    if command not in _ALLOWED_COMMANDS:
        raise ValueError("DEVICE_PROBE_COMMAND_NOT_ALLOWLISTED")
    try:
        completed = subprocess.run(
            list(command),
            check=True,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        return completed.stdout.strip()
    except Exception:
        return None


def _positive_int(value: Any) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        return None
    return value


def _nonnegative_int(value: Any) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        return None
    return value


def _sysctl_positive_int(name: str) -> int | None:
    text = _run_allowlisted(("/usr/sbin/sysctl", "-n", name))
    try:
        return _positive_int(int(text)) if text is not None else None
    except ValueError:
        return None


def _parse_vm_stat_text(text: str) -> int | None:
    if not text:
        return None
    page_match = re.search(r"page size of (\d+) bytes", text)
    page_size = int(page_match.group(1)) if page_match else 4096
    if page_size <= 0:
        return None
    values: dict[str, int] = {}
    for line in text.splitlines():
        if ":" not in line:
            continue
        key, raw = line.split(":", 1)
        digits = re.sub(r"[^0-9]", "", raw)
        if digits:
            values[key.strip()] = int(digits)
    required_keys = {"Pages free", "Pages inactive", "Pages speculative", "Pages purgeable"}
    if not required_keys & set(values):
        return None
    available_pages = sum(values.get(key, 0) for key in required_keys)
    return _nonnegative_int(available_pages * page_size)


def _parse_vm_stat() -> int | None:
    return _parse_vm_stat_text(_run_allowlisted(("/usr/bin/vm_stat",)) or "")


def _optional_psutil_values() -> tuple[int | None, int | None, float | None, bool | None]:
    try:
        import psutil  # type: ignore

        rss = int(psutil.Process(os.getpid()).memory_info().rss)
        available = int(psutil.virtual_memory().available)
        battery = psutil.sensors_battery()
        return (
            _nonnegative_int(rss),
            _nonnegative_int(available),
            float(battery.percent) if battery is not None else None,
            bool(battery.power_plugged) if battery is not None else None,
        )
    except Exception:
        return None, None, None, None


def load_native_telemetry(environ: Mapping[str, str] | None = None) -> dict[str, Any] | None:
    env = os.environ if environ is None else environ
    value = env.get(NATIVE_TELEMETRY_ENV, "")
    if not value:
        return None
    if len(value) > 4096:
        return None
    try:
        payload = json.loads(value)
    except Exception:
        return None
    if not isinstance(payload, dict) or set(payload) - NATIVE_ALLOWED_KEYS:
        return None
    return payload


def _enum_or_unknown(enum_type, value: Any):
    try:
        return enum_type(str(value))
    except ValueError:
        return enum_type.UNKNOWN


def _estimated_memory_pressure(total: int | None, available: int | None) -> MemoryPressure:
    if not total or available is None:
        return MemoryPressure.UNKNOWN
    ratio = available / total
    if ratio < 0.10:
        return MemoryPressure.CRITICAL
    if ratio < 0.20:
        return MemoryPressure.WARN
    return MemoryPressure.NORMAL


def collect_device_profile(native_telemetry: Mapping[str, Any] | None = None) -> DeviceProfile:
    native = dict(native_telemetry or {})
    errors: list[str] = []
    invalid_measurement = False
    if set(native) - NATIVE_ALLOWED_KEYS:
        native = {}
        errors.append("NATIVE_TELEMETRY_KEYS_INVALID")

    total = _positive_int(native.get("total_memory_bytes"))
    available = _nonnegative_int(native.get("available_memory_bytes"))
    rss = _nonnegative_int(native.get("process_rss_bytes"))
    source = "native_tauri" if native else "unknown"

    if native.get("total_memory_bytes") is not None and total is None:
        errors.append("NATIVE_TOTAL_MEMORY_INVALID")
        invalid_measurement = True
    if native.get("available_memory_bytes") is not None and available is None:
        errors.append("NATIVE_AVAILABLE_MEMORY_INVALID")
        invalid_measurement = True

    system = platform.system()
    if system == "Darwin":
        if total is None:
            total = _sysctl_positive_int("hw.memsize")
        if available is None:
            available = _parse_vm_stat()
        if not native:
            source = "stdlib_macos"
    else:
        source = "portable_fallback" if not native else source

    psutil_rss, psutil_available, psutil_battery, _plugged = _optional_psutil_values()
    if rss is None:
        rss = psutil_rss
    if available is None:
        available = psutil_available

    if total is not None and available is not None and available > total:
        errors.append("AVAILABLE_MEMORY_EXCEEDS_TOTAL")
        available = None
        invalid_measurement = True
    if invalid_measurement:
        validity = ProfileValidity.INVALID
    elif total is None or available is None:
        validity = ProfileValidity.UNKNOWN
    elif total <= 0 or available < 0:
        validity = ProfileValidity.INVALID
    else:
        validity = ProfileValidity.VALID

    native_pressure = _enum_or_unknown(MemoryPressure, native.get("memory_pressure"))
    memory_pressure = (
        native_pressure
        if native_pressure is not MemoryPressure.UNKNOWN
        else _estimated_memory_pressure(total, available)
    )
    thermal_state = _enum_or_unknown(ThermalState, native.get("thermal_state"))
    battery_value = native.get("battery_percent", psutil_battery)
    battery_percent = (
        float(battery_value)
        if isinstance(battery_value, (int, float)) and not isinstance(battery_value, bool)
        else None
    )
    if battery_percent is not None and not 0.0 <= battery_percent <= 100.0:
        errors.append("BATTERY_PERCENT_INVALID")
        battery_percent = None

    chip_family = str(native.get("chip_family") or "").strip()
    if not chip_family and system == "Darwin":
        chip_family = (
            _run_allowlisted(("/usr/sbin/sysctl", "-n", "machdep.cpu.brand_string"))
            or "unknown"
        )
    if not chip_family:
        chip_family = platform.processor() or "unknown"

    profile = DeviceProfile(
        schema_version="butler.device_profile.v1",
        platform=system.lower() or "unknown",
        architecture=platform.machine().lower() or "unknown",
        chip_family=chip_family[:80],
        total_memory_bytes=total,
        available_memory_bytes=available,
        process_rss_bytes=rss,
        memory_pressure=memory_pressure,
        thermal_state=thermal_state,
        low_power_mode=(
            native.get("low_power_mode")
            if isinstance(native.get("low_power_mode"), bool)
            else None
        ),
        battery_percent=battery_percent,
        metal_available=(
            native.get("metal_available")
            if isinstance(native.get("metal_available"), bool)
            else None
        ),
        profiler_source=source,
        collected_at_epoch_ms=int(time.time() * 1000),
        validity=validity,
        probe_errors=tuple(sorted(set(errors))),
    )
    profile.validate()
    return profile


def unknown_device_profile(reason: str = "DEVICE_PROFILE_NOT_SAMPLED") -> DeviceProfile:
    return DeviceProfile(
        schema_version="butler.device_profile.v1",
        platform=platform.system().lower() or "unknown",
        architecture=platform.machine().lower() or "unknown",
        chip_family="unknown",
        total_memory_bytes=None,
        available_memory_bytes=None,
        process_rss_bytes=None,
        memory_pressure=MemoryPressure.UNKNOWN,
        thermal_state=ThermalState.UNKNOWN,
        low_power_mode=None,
        battery_percent=None,
        metal_available=None,
        profiler_source="unknown",
        collected_at_epoch_ms=int(time.time() * 1000),
        validity=ProfileValidity.UNKNOWN,
        probe_errors=(reason,),
    )


class DeviceProfileSampler:
    """Background profiler so sysctl/vm_stat never run on a request thread."""

    def __init__(self, *, interval_seconds: float = 30.0) -> None:
        self._interval_seconds = max(5.0, float(interval_seconds))
        self._latest: DeviceProfile | None = None
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread = threading.Thread(
            target=self._run,
            name="model-tier-device-profiler",
            daemon=True,
        )

    def start(self) -> None:
        if not self._thread.is_alive():
            self._thread.start()

    def stop(self, timeout: float = 2.0) -> None:
        self._stop.set()
        if self._thread.is_alive():
            self._thread.join(timeout=timeout)

    def latest(self) -> DeviceProfile:
        with self._lock:
            return self._latest or unknown_device_profile()

    def sample_once(self) -> DeviceProfile:
        profile = collect_device_profile(load_native_telemetry())
        with self._lock:
            self._latest = profile
        return profile

    def _run(self) -> None:
        while not self._stop.is_set():
            try:
                self.sample_once()
            except Exception:
                with self._lock:
                    self._latest = unknown_device_profile("DEVICE_PROFILE_SAMPLE_FAILED")
            self._stop.wait(self._interval_seconds)
