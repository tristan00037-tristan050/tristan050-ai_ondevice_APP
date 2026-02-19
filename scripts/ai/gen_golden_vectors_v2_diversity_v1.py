import json, copy, os, sys
from pathlib import Path

SRC = Path("scripts/ai/golden_vectors_v2.json")

d = json.loads(SRC.read_text(encoding="utf-8"))

# normalize items list
if isinstance(d, list):
    items = d
    wrap_key = None
elif isinstance(d, dict):
    for k in ("vectors","cases","items","data"):
        if k in d and isinstance(d[k], list):
            items = d[k]
            wrap_key = k
            break
    else:
        items = [d]
        wrap_key = None
else:
    print("BLOCK: unexpected root json type")
    sys.exit(1)

if not items or not isinstance(items[0], dict):
    print("BLOCK: first vector is not an object")
    sys.exit(1)

base = copy.deepcopy(items[0])

# Ensure feature_digest_v1 exists
fd = base.get("feature_digest_v1") or {}
if not isinstance(fd, dict):
    print("BLOCK: feature_digest_v1 must be object when present")
    sys.exit(1)

# Minimal required keys (from FEATURE_DIGEST contract)
fd.setdefault("model_pack_id", "pack_demo")
fd.setdefault("pack_version_id", "v1")
fd.setdefault("mode", "default")

# Diversity axes (all allowlisted keys)
device_classes = ["dc_low", "dc_mid", "dc_high"]
modes = ["default", "shadow"]
policies = ["pol_a", "pol_b"]
backends = ["be_cpu", "be_gpu"]
quant = ["q8", "q4"]

# Generate 12 vectors (>=10)
out = []
n = 0
for dc in device_classes:
    for md in modes:
        for pol in policies:
            v = copy.deepcopy(base)
            vfd = dict(fd)
            vfd["device_class_id"] = dc
            vfd["mode"] = md
            vfd["policy_id"] = pol
            vfd["backend_id"] = backends[n % len(backends)]
            vfd["quantization_id"] = quant[n % len(quant)]
            v["feature_digest_v1"] = vfd

            # Optional stable tag/id if object has a free-form id-like field
            for id_key in ("case_id", "id", "name", "vector_id", "test_id"):
                if id_key in v and isinstance(v[id_key], str):
                    v[id_key] = f"gv2_div_{n:02d}"
                    break

            out.append(v)
            n += 1
            if n >= 12:
                break
        if n >= 12:
            break
    if n >= 12:
        break

items2 = out

# Write back
if isinstance(d, list):
    d2 = items2
elif isinstance(d, dict) and wrap_key:
    d2 = dict(d)
    d2[wrap_key] = items2
else:
    d2 = items2

SRC.write_text(json.dumps(d2, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print("OK: wrote", SRC, "vectors=", len(items2))
