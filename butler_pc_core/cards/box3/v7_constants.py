from __future__ import annotations

BOX3_BASE_MODEL_VERSION = "butler-1.7b-v9-2-r2b"

# v9.2-r2b canonical = v7 위 box3 grounding LoRA + r2b 제목/마커 정규화 데이터.
V9_2_R2B_MODEL_NAME = "butler-1.7b-v9-2-r2b-q4_k_m.gguf"
V9_2_R2B_Q4_K_M_SHA256_FULL = "aae4ea7a4ebe0586db3317d5209b5565abcd326ea73decb7ffa99f433c218847"

# v9.1 historical reference only — operational default 0.
V9_1_MODEL_NAME_HISTORICAL_REFERENCE_ONLY = "butler-1.7b-v9-1-q4_k_m.gguf"
V9_1_Q4_K_M_SHA256_HISTORICAL_REFERENCE_ONLY = "4ac03239fd374a55f691ddde6599f3ed488ca5cdec79103a0bdcec40a5b96d38"

# v7 historical reference only — operational default 0.
V7_Q4_K_M_SHA256_HISTORICAL_REFERENCE_ONLY = "a8440e984a2d0899049df7166aeff32d9bfb2881e614aa55b029b4a7eead5621"
V7_F16_SHA256_HISTORICAL_REFERENCE_ONLY = "6ff70adf08130c11a4ece523f33b2b8d4d2118187805a458661fe7c62d5be7f1"
V7_MODEL_NAME_HISTORICAL_REFERENCE_ONLY = "butler-1.7b-v7-q4_k_m.gguf"

# Backward-compat aliases for old v7 tests/imports.
V7_Q4_K_M_SHA256_FULL = V7_Q4_K_M_SHA256_HISTORICAL_REFERENCE_ONLY
V7_F16_SHA256_FULL = V7_F16_SHA256_HISTORICAL_REFERENCE_ONLY
V7_MODEL_NAME = V7_MODEL_NAME_HISTORICAL_REFERENCE_ONLY

BASE_MODEL_SHA256_FULL = V9_2_R2B_Q4_K_M_SHA256_FULL
BASE_MODEL_NAME = V9_2_R2B_MODEL_NAME
BASE_MODEL_SHA_SCOPE = "file"
BASE_MODEL_PATH_ENV = "BUTLER_BOX3_V9_Q4_MODEL_PATH"

HELPER3_5_EMBEDDED_IN_BASE = True
HELPER3_5_RUNTIME_STACK_ALLOWED = False
PRODUCTION_CLAIM_ALLOWED = False

# Historical references only. They must never become operational defaults.
V5_Q4_K_M_SHA256_HISTORICAL_REFERENCE_ONLY = "5e233aab773d0cdb2b188649edbd36633f3dbb58be7ff4c4295a83de648212d2"
V4_Q4_K_M_SHA256_HISTORICAL_REFERENCE_ONLY = "60b9baee17696ca8e3a3aa0950a4d441ad3c4baa80bbd73ec9fa33c17cba0c1f"

# v9.2-r2b is the Group-A sealed canonical model promoted from the v9.2-r2b 6-case PASS run.
MODEL_LINEAGE = {
    "base": "butler-1.7b-v9-2-r2b",
    "recipe": "v7/v9.1 canonical lineage + box3 r2b title/marker normalization data retrain",
    "included_adapters": ["butler_v3", "helper3_format", "helper5_tool_call", "grounded_lora"],
    "runtime_lora_stack_allowed": False,
}
