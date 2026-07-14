import Foundation
import Metal

guard let device = MTLCreateSystemDefaultDevice() else {
    let blocked: [String: Any] = [
        "schema_version": "butler.model-tier-b.metal-probe.v2.5",
        "status": "BLOCKED",
        "fail_class": "METAL_EVIDENCE_INVALID"
    ]
    let data = try JSONSerialization.data(withJSONObject: blocked, options: [.sortedKeys])
    FileHandle.standardOutput.write(data)
    FileHandle.standardOutput.write(Data([0x0A]))
    exit(14)
}

let payload: [String: Any] = [
    "schema_version": "butler.model-tier-b.metal-probe.v2.5",
    "status": "PASS",
    "registry_id": device.registryID,
    "current_allocated_size_bytes": device.currentAllocatedSize,
    "recommended_max_working_set_size_bytes": device.recommendedMaxWorkingSetSize,
    "has_unified_memory": device.hasUnifiedMemory,
    "max_threads_per_threadgroup_width": device.maxThreadsPerThreadgroup.width,
    "max_threads_per_threadgroup_height": device.maxThreadsPerThreadgroup.height,
    "max_threads_per_threadgroup_depth": device.maxThreadsPerThreadgroup.depth
]
let data = try JSONSerialization.data(withJSONObject: payload, options: [.sortedKeys])
FileHandle.standardOutput.write(data)
FileHandle.standardOutput.write(Data([0x0A]))

