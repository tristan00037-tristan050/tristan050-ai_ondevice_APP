#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform as py_platform
import re
import socket
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

ROOT_HINT = Path(__file__).resolve().parents[1]
if str(ROOT_HINT) not in sys.path:
    sys.path.insert(0, str(ROOT_HINT))

from src.ip3.telemetry_schema import (
    SCHEMA_VERSION,
    ALLOWED_EVIDENCE_CLASSES,
    compute_payload_canonical_sha256,
    current_platform_name,
    expected_evidence_path,
    normalize_platform_name,
    validate_telemetry_payload,
    write_json,
)

COLLECTOR_NAME = "ip3_v1_3_evidence_classed_telemetry_collector"
COLLECTOR_VERSION = "1.3.1-sealable"


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def read_text_safely(path: Path, limit: int = 2048) -> Optional[str]:
    try:
        return path.read_text(encoding="utf-8", errors="ignore")[:limit]
    except Exception:
        return None


def run_cmd(cmd: List[str], timeout: float = 5.0) -> Tuple[int, str, str]:
    try:
        cp = subprocess.run(cmd, text=True, capture_output=True, timeout=timeout, check=False)
        return cp.returncode, cp.stdout.strip(), cp.stderr.strip()
    except FileNotFoundError as exc:
        return 127, "", str(exc)
    except subprocess.TimeoutExpired as exc:
        out = exc.stdout if isinstance(exc.stdout, str) else ""
        return 124, out.strip(), "timeout"
    except Exception as exc:
        return 1, "", str(exc)


def powershell_json(script: str, timeout: float = 10.0) -> Any:
    candidates = ["pwsh", "powershell"]
    last_error = ""
    for exe in candidates:
        code, out, err = run_cmd([exe, "-NoProfile", "-NonInteractive", "-Command", script], timeout=timeout)
        if code == 0 and out:
            try:
                return json.loads(out)
            except json.JSONDecodeError as exc:
                last_error = f"{exe} json error: {exc}; out={out[:200]!r}"
        else:
            last_error = f"{exe} failed code={code} err={err[:200]!r}"
    raise RuntimeError(last_error or "PowerShell unavailable")


def collect_cpu(norm: str) -> Dict[str, Any]:
    logical = os.cpu_count() or 0
    base: Dict[str, Any] = {
        "status": "ok" if logical > 0 else "failed",
        "source": "python.os.cpu_count",
        "logical_processors": int(logical),
        "sample_interval_ms": 150,
    }
    if norm == "linux":
        try:
            def read_total_idle() -> Tuple[int, int]:
                parts = Path("/proc/stat").read_text().splitlines()[0].split()[1:]
                vals = [int(x) for x in parts]
                idle = vals[3] + (vals[4] if len(vals) > 4 else 0)
                return sum(vals), idle
            t1, i1 = read_total_idle()
            time.sleep(0.15)
            t2, i2 = read_total_idle()
            dt = max(t2 - t1, 1)
            di = max(i2 - i1, 0)
            base.update({
                "load_percent": round(max(0.0, min(100.0, (1.0 - di / dt) * 100.0)), 2),
                "source": "linux.proc_stat+python.os.cpu_count",
            })
        except Exception as exc:
            base.update({"status": "limited", "load_percent": None, "reason": f"proc_stat_unavailable:{type(exc).__name__}"})
    elif norm == "darwin":
        code, out, err = run_cmd(["sysctl", "-n", "hw.logicalcpu"], timeout=3)
        if code == 0 and out.strip().isdigit():
            base.update({"logical_processors": int(out.strip()), "source": "darwin.sysctl.hw.logicalcpu"})
        code2, out2, _ = run_cmd(["sysctl", "-n", "machdep.cpu.brand_string"], timeout=3)
        if code2 == 0 and out2:
            base["cpu_brand_digest"] = sha256_text(out2)
        base.setdefault("load_percent", None)
    elif norm == "windows":
        try:
            data = powershell_json("Get-CimInstance Win32_Processor | Select-Object -First 1 NumberOfLogicalProcessors,LoadPercentage,MaxClockSpeed | ConvertTo-Json -Compress")
            if isinstance(data, dict):
                if data.get("NumberOfLogicalProcessors"):
                    base["logical_processors"] = int(data["NumberOfLogicalProcessors"])
                if data.get("LoadPercentage") is not None:
                    base["load_percent"] = float(data["LoadPercentage"])
                if data.get("MaxClockSpeed") is not None:
                    base["max_clock_mhz"] = int(data["MaxClockSpeed"])
                base["source"] = "windows.cim.Win32_Processor"
        except Exception as exc:
            base.update({"status": "limited", "load_percent": None, "reason": f"win32_processor_limited:{type(exc).__name__}"})
    return base


def collect_memory(norm: str) -> Dict[str, Any]:
    if norm == "linux":
        try:
            kv: Dict[str, int] = {}
            for line in Path("/proc/meminfo").read_text().splitlines():
                key, val = line.split(":", 1)
                kv[key] = int(val.strip().split()[0]) * 1024
            total = int(kv.get("MemTotal", 0))
            avail = int(kv.get("MemAvailable", kv.get("MemFree", 0)))
            return {"status": "ok", "source": "linux.proc_meminfo", "total_bytes": total, "available_bytes": avail, "used_bytes": max(total - avail, 0)}
        except Exception as exc:
            return {"status": "failed", "source": "linux.proc_meminfo", "reason": f"{type(exc).__name__}:{exc}"}
    if norm == "darwin":
        code, out, err = run_cmd(["sysctl", "-n", "hw.memsize"], timeout=3)
        if code == 0 and out.strip().isdigit():
            return {"status": "ok", "source": "darwin.sysctl.hw.memsize", "total_bytes": int(out.strip()), "available_bytes": None, "used_bytes": None}
        return {"status": "failed", "source": "darwin.sysctl.hw.memsize", "reason": err or "hw.memsize unavailable"}
    if norm == "windows":
        try:
            data = powershell_json("Get-CimInstance Win32_OperatingSystem | Select-Object -First 1 TotalVisibleMemorySize,FreePhysicalMemory | ConvertTo-Json -Compress")
            total = int(data.get("TotalVisibleMemorySize", 0)) * 1024
            free = int(data.get("FreePhysicalMemory", 0)) * 1024
            return {"status": "ok", "source": "windows.cim.Win32_OperatingSystem", "total_bytes": total, "available_bytes": free, "used_bytes": max(total - free, 0)}
        except Exception as exc:
            return {"status": "failed", "source": "windows.cim.Win32_OperatingSystem", "reason": f"{type(exc).__name__}:{exc}"}
    return {"status": "failed", "source": "unknown", "reason": f"unsupported platform {norm}"}


def collect_battery(norm: str) -> Dict[str, Any]:
    if norm == "linux":
        base = Path("/sys/class/power_supply")
        supplies = sorted(base.glob("BAT*")) if base.exists() else []
        if not supplies:
            return {"status": "unavailable", "source": "linux.sysfs.power_supply", "reason": "no_battery_detected", "battery_present": False}
        bat = supplies[0]
        def read_name(name: str) -> Optional[str]:
            try:
                return (bat / name).read_text().strip()
            except Exception:
                return None
        percent = read_name("capacity")
        return {"status": "ok", "source": "linux.sysfs.power_supply", "battery_present": True, "charge_percent": int(percent) if percent and percent.isdigit() else None, "state": read_name("status"), "battery_count": len(supplies)}
    if norm == "darwin":
        code, out, err = run_cmd(["pmset", "-g", "batt"], timeout=4)
        if code != 0:
            return {"status": "unavailable", "source": "darwin.pmset", "reason": err or "pmset unavailable", "battery_present": False}
        if "No batteries" in out:
            return {"status": "unavailable", "source": "darwin.pmset", "reason": "no_battery_detected", "battery_present": False}
        m = re.search(r"(\d+)%", out)
        return {"status": "ok", "source": "darwin.pmset", "battery_present": True, "charge_percent": int(m.group(1)) if m else None, "state_digest": sha256_text(out)}
    if norm == "windows":
        try:
            data = powershell_json("$b=Get-CimInstance Win32_Battery | Select-Object BatteryStatus,EstimatedChargeRemaining,EstimatedRunTime,DesignCapacity,FullChargeCapacity; @($b) | ConvertTo-Json -Compress")
            arr = data if isinstance(data, list) else ([data] if isinstance(data, dict) else [])
            if not arr:
                return {"status": "unavailable", "source": "windows.cim.Win32_Battery", "reason": "no_battery_detected", "battery_present": False}
            first = arr[0]
            return {"status": "ok", "source": "windows.cim.Win32_Battery", "battery_present": True, "battery_status": first.get("BatteryStatus"), "charge_percent": first.get("EstimatedChargeRemaining"), "estimated_runtime_minutes": first.get("EstimatedRunTime"), "design_capacity": first.get("DesignCapacity"), "full_charge_capacity": first.get("FullChargeCapacity"), "battery_count": len(arr)}
        except Exception as exc:
            return {"status": "limited", "source": "windows.cim.Win32_Battery", "reason": f"{type(exc).__name__}:{exc}", "battery_present": None}
    return {"status": "failed", "source": "unknown", "reason": f"unsupported platform {norm}"}


def collect_thermal(norm: str) -> Dict[str, Any]:
    if norm == "linux":
        temps: List[float] = []
        for p in Path("/sys/class/thermal").glob("thermal_zone*/temp"):
            try:
                raw = p.read_text().strip()
                val = float(raw)
                if val > 1000:
                    val = val / 1000.0
                if -50 <= val <= 150:
                    temps.append(round(val, 2))
            except Exception:
                continue
        if temps:
            return {"status": "ok", "source": "linux.sysfs.thermal_zone", "temperature_c_min": min(temps), "temperature_c_max": max(temps), "sensor_count": len(temps)}
        return {"status": "unavailable", "source": "linux.sysfs.thermal_zone", "reason": "no_thermal_sensor_readable", "sensor_count": 0}
    if norm == "darwin":
        code, out, err = run_cmd(["pmset", "-g", "therm"], timeout=4)
        if code == 0 and out:
            return {"status": "limited", "source": "darwin.pmset.therm", "reason": "thermal_pressure_only", "thermal_state_digest": sha256_text(out)}
        return {"status": "unavailable", "source": "darwin.pmset.therm", "reason": err or "thermal_sensor_requires_privilege_or_vendor_api"}
    if norm == "windows":
        try:
            data = powershell_json("$t=Get-CimInstance -Namespace root/wmi -ClassName MSAcpi_ThermalZoneTemperature -ErrorAction SilentlyContinue | Select-Object CurrentTemperature; @($t) | ConvertTo-Json -Compress", timeout=10)
            arr = data if isinstance(data, list) else ([data] if isinstance(data, dict) else [])
            temps: List[float] = []
            for row in arr:
                val = row.get("CurrentTemperature") if isinstance(row, dict) else None
                if val is not None:
                    c = (float(val) / 10.0) - 273.15
                    if -50 <= c <= 150:
                        temps.append(round(c, 2))
            if temps:
                return {"status": "ok", "source": "windows.wmi.MSAcpi_ThermalZoneTemperature", "temperature_c_min": min(temps), "temperature_c_max": max(temps), "sensor_count": len(temps)}
            return {"status": "unavailable", "source": "windows.wmi.MSAcpi_ThermalZoneTemperature", "reason": "no_thermal_sensor_readable", "sensor_count": 0}
        except Exception as exc:
            return {"status": "limited", "source": "windows.wmi.MSAcpi_ThermalZoneTemperature", "reason": f"{type(exc).__name__}:{exc}", "sensor_count": None}
    return {"status": "failed", "source": "unknown", "reason": f"unsupported platform {norm}"}


def collect_network(norm: str) -> Dict[str, Any]:
    hostname = socket.gethostname() or "unknown-host"
    block: Dict[str, Any] = {"status": "ok", "source": "python.socket", "hostname_digest": sha256_text(hostname), "raw_hostname_recorded": False}
    try:
        infos = socket.getaddrinfo(hostname, None)
        families = sorted({str(x[0]) for x in infos})
        addrs = sorted({str(x[4][0]) for x in infos if x and len(x) > 4})
        block.update({"address_count": len(addrs), "address_set_digest": sha256_text("|".join(addrs)), "family_set_digest": sha256_text("|".join(families)), "raw_ip_recorded": False})
    except Exception as exc:
        block.update({"status": "limited", "reason": f"addrinfo_limited:{type(exc).__name__}", "address_count": 0, "raw_ip_recorded": False})
    if norm == "windows":
        try:
            data = powershell_json("Get-NetAdapter -ErrorAction SilentlyContinue | Select-Object Name,Status,MacAddress,LinkSpeed | ConvertTo-Json -Compress", timeout=10)
            arr = data if isinstance(data, list) else ([data] if isinstance(data, dict) else [])
            normalized = []
            for item in arr:
                if isinstance(item, dict):
                    normalized.append({"Status": item.get("Status"), "LinkSpeed": item.get("LinkSpeed")})
            block.update({"source": "python.socket+windows.Get-NetAdapter", "adapter_count": len(arr), "adapter_state_digest": sha256_text(json.dumps(normalized, sort_keys=True))})
        except Exception as exc:
            block["windows_adapter_reason"] = f"get_netadapter_limited:{type(exc).__name__}"
    return block


def detect_virtualization(norm: str) -> Dict[str, Any]:
    result: Dict[str, Any] = {"virtualization_detected": None, "signals": [], "source": "multi_probe"}
    signals: List[str] = []
    if norm == "linux":
        code, out, _ = run_cmd(["systemd-detect-virt"], timeout=2)
        if code == 0 and out and out != "none":
            signals.append(f"systemd-detect-virt:{out}")
        product = read_text_safely(Path("/sys/class/dmi/id/product_name")) or ""
        vendor = read_text_safely(Path("/sys/class/dmi/id/sys_vendor")) or ""
        blob = (product + " " + vendor).lower()
        for needle in ("kvm", "qemu", "vmware", "virtualbox", "hyper-v", "parallels", "amazon ec2", "google", "azure"):
            if needle in blob:
                signals.append(f"dmi:{needle}")
                break
    elif norm == "darwin":
        code, out, _ = run_cmd(["sysctl", "-n", "kern.hv_vmm_present"], timeout=2)
        if code == 0 and out.strip() == "1":
            signals.append("darwin.kern.hv_vmm_present")
        code2, out2, _ = run_cmd(["sysctl", "-n", "hw.model"], timeout=2)
        if code2 == 0 and any(x in out2.lower() for x in ("virtual", "vmware", "parallels")):
            signals.append("darwin.hw.model.virtual")
    elif norm == "windows":
        try:
            data = powershell_json("Get-CimInstance Win32_ComputerSystem | Select-Object Manufacturer,Model,HypervisorPresent | ConvertTo-Json -Compress", timeout=8)
            if isinstance(data, dict):
                digest_src = json.dumps(data, sort_keys=True)
                result["machine_fingerprint_digest"] = sha256_text(digest_src)
                blob = f"{data.get('Manufacturer','')} {data.get('Model','')}".lower()
                if data.get("HypervisorPresent") is True:
                    signals.append("windows.cim.HypervisorPresent")
                for needle in ("virtual", "vmware", "virtualbox", "parallels", "qemu", "kvm", "hyper-v", "microsoft corporation virtual"):
                    if needle in blob:
                        signals.append(f"windows.cim.vendor_model:{needle}")
                        break
        except Exception as exc:
            result["reason"] = f"windows_virtualization_probe_limited:{type(exc).__name__}"
    result["signals"] = signals
    result["virtualization_detected"] = True if signals else False
    return result


def detect_ci_environment() -> Dict[str, Any]:
    providers = []
    env = os.environ
    if env.get("GITHUB_ACTIONS") == "true":
        providers.append("github_actions")
    if env.get("CI") == "true" and not providers:
        providers.append("generic_ci")
    if env.get("TF_BUILD") == "True":
        providers.append("azure_pipelines")
    if env.get("GITLAB_CI") == "true":
        providers.append("gitlab_ci")
    return {"is_ci": bool(providers), "ci_provider": providers[0] if providers else None, "ci_provider_digest": sha256_text("|".join(sorted(providers))) if providers else None}


def collector_file_sha256() -> str:
    return sha256_bytes(Path(__file__).read_bytes())


def build_payload(root: Path, device_id: str, evidence_class: str, physical_device_assertion: bool) -> Dict[str, Any]:
    norm = current_platform_name()
    ci = detect_ci_environment()
    virt = detect_virtualization(norm)
    evidence: Dict[str, Any] = {
        "class": evidence_class,
        "tier": "real_runtime_measurement",
        "raw_content_stored": False,
        "ci_provider": ci["ci_provider"] if evidence_class == "ci_lab" else None,
        "physical_device_assertion": bool(physical_device_assertion),
    }
    if evidence_class != "ci_lab":
        evidence.pop("ci_provider", None)

    payload: Dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "stage": "ip3_v1_3_windows_telemetry_strict_gate",
        "collected_at_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "device_id_digest": sha256_text(device_id),
        "platform": {
            "normalized": norm,
            "python_platform_system": py_platform.system(),
            "python_machine_digest": sha256_text(py_platform.machine() or "unknown"),
            "python_release_digest": sha256_text(py_platform.release() or "unknown"),
        },
        "evidence": evidence,
        "privacy": {flag: False for flag in ("raw_device_id_recorded", "raw_hostname_recorded", "raw_ip_recorded", "raw_prompt_recorded", "raw_user_text_recorded", "raw_log_recorded", "raw_path_recorded")},
        "environment": {
            "is_ci": ci["is_ci"],
            "ci_provider": ci["ci_provider"],
            "ci_provider_digest": ci["ci_provider_digest"],
            "virtualization_detected": virt.get("virtualization_detected"),
            "virtualization_signal_digest": sha256_text("|".join(virt.get("signals", []))),
            "virtualization_signal_count": len(virt.get("signals", [])),
            "physical_host_attested": bool(physical_device_assertion) and not ci["is_ci"],
        },
        "measurements": {
            "cpu": collect_cpu(norm),
            "memory": collect_memory(norm),
            "battery": collect_battery(norm),
            "thermal": collect_thermal(norm),
            "network": collect_network(norm),
        },
        "collector": {
            "name": COLLECTOR_NAME,
            "version": COLLECTOR_VERSION,
            "platform_override_used": False,
            "python_version_digest": sha256_text(sys.version),
        },
        "source_integrity": {
            "collector_file_sha256": collector_file_sha256(),
            "payload_canonical_sha256": None,
        },
    }
    payload["source_integrity"]["payload_canonical_sha256"] = compute_payload_canonical_sha256(payload)
    return payload


def main() -> int:
    ap = argparse.ArgumentParser(description="Collect privacy-preserving real telemetry for IP3 v1.3.")
    ap.add_argument("root", nargs="?", default=".")
    ap.add_argument("--device-id", required=True)
    ap.add_argument("--evidence-class", choices=sorted(ALLOWED_EVIDENCE_CLASSES), required=True)
    ap.add_argument("--physical-device-assertion", action="store_true", help="Required for physical_lab; never use for CI/VM evidence.")
    ap.add_argument("--allow-ci-lab-outside-ci", action="store_true", help="Test-only escape hatch. Do not use for release evidence.")
    args = ap.parse_args()

    root = Path(args.root).resolve()
    root.joinpath("evidence").mkdir(parents=True, exist_ok=True)

    if args.evidence_class == "production":
        print("COLLECT_REAL_TELEMETRY_FAIL production evidence is disabled in this v1.3 lab pack", file=sys.stderr)
        return 2
    ci = detect_ci_environment()
    if args.evidence_class == "ci_lab" and not ci["is_ci"] and not args.allow_ci_lab_outside_ci:
        print("COLLECT_REAL_TELEMETRY_FAIL evidence_class=ci_lab requires a detected CI environment", file=sys.stderr)
        return 2
    if args.evidence_class in {"ci_lab", "vm_lab"} and args.physical_device_assertion:
        print("COLLECT_REAL_TELEMETRY_FAIL lower evidence classes cannot assert physical device", file=sys.stderr)
        return 2
    if args.evidence_class == "physical_lab" and not args.physical_device_assertion:
        print("COLLECT_REAL_TELEMETRY_FAIL physical_lab requires --physical-device-assertion", file=sys.stderr)
        return 2

    payload = build_payload(root, args.device_id, args.evidence_class, args.physical_device_assertion)
    result = validate_telemetry_payload(
        payload,
        expected_platform=current_platform_name(),
        expected_evidence_class=args.evidence_class,
        require_physical_windows=(args.evidence_class == "physical_lab" and current_platform_name() == "windows"),
        require_battery_present=(args.evidence_class == "physical_lab" and current_platform_name() == "windows"),
    )
    if not result.ok:
        for err in result.errors:
            print(f"COLLECT_REAL_TELEMETRY_SELF_GATE_FAIL {err}", file=sys.stderr)
        return 2

    current_path = root / "evidence" / "real_telemetry_current_platform.json"
    platform_path = expected_evidence_path(root, result.platform or current_platform_name())
    write_json(current_path, payload)
    write_json(platform_path, payload)
    print(f"REAL_TELEMETRY_COLLECTED platform={result.platform} evidence_class={args.evidence_class} evidence={platform_path.relative_to(root)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
