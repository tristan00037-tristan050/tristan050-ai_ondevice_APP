import Foundation
#if os(macOS)
import IOKit.ps
#endif

func thermalName(_ state: ProcessInfo.ThermalState) -> String {
    switch state {
    case .nominal: return "nominal"
    case .fair: return "fair"
    case .serious: return "serious"
    case .critical: return "critical"
    @unknown default: return "unknown"
    }
}

func powerSource() -> String {
#if os(macOS)
    guard let snapshot = IOPSCopyPowerSourcesInfo()?.takeRetainedValue() else { return "UNKNOWN" }
    guard let source = IOPSGetProvidingPowerSourceType(snapshot)?.takeUnretainedValue() as String? else { return "UNKNOWN" }
    return source
#else
    return "UNSUPPORTED"
#endif
}

let info = ProcessInfo.processInfo
let payload: [String: Any] = [
    "schema_version": "butler.model-tier-b.environment-probe.v2.5",
    "platform": "macOS",
    "macos_version": info.operatingSystemVersionString,
    "processor_count": info.processorCount,
    "active_processor_count": info.activeProcessorCount,
    "physical_memory_bytes": info.physicalMemory,
    "thermal_state": thermalName(info.thermalState),
    "low_power_mode": info.isLowPowerModeEnabled,
    "power_source": powerSource()
]
let data = try JSONSerialization.data(withJSONObject: payload, options: [.sortedKeys])
FileHandle.standardOutput.write(data)
FileHandle.standardOutput.write(Data([0x0A]))

