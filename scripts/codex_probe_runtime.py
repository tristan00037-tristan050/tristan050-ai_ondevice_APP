from box3_real_operation_v1_2.runtime_probe import detect_runtime
import json

probe = detect_runtime("runtime_for_box3_real_operation")
print(json.dumps(probe.__dict__ | {"runtime_available": probe.all_available}, ensure_ascii=False, indent=2))
