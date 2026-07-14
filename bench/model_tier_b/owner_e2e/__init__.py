"""Owner M3 E2E orchestrator for the model-tier-B benchmark (bench-side).

The owner driver performs source-identity verification BEFORE importing any product
code, spawns an isolated child worker that imports the real Butler product and runs a
single real 1.7B Box3 smoke, then writes a verifier-passing evidence root from the
real observations and independently verifies it. No product code is imported in the
owner process itself. RUNTIME_ACTIVATION_ALLOWED stays 0; g1_ready stays false.
"""
