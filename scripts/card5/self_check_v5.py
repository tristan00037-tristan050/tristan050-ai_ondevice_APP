from __future__ import annotations

from pathlib import Path


def main() -> int:
    root_manifest = Path("manifest.json")
    if root_manifest.exists():
        body = root_manifest.read_text(encoding="utf-8", errors="ignore")
        assert "option_d" not in body

    required = [
        "tests/card5/test_apply_alias_backward_compat_v5.py",
        "tests/card5/test_inference_backward_compat_v5.py",
        "tests/card5/test_main_repo_regression_v5.py",
        "tests/card5/test_option_d_manifest_resolver_v5.py",
        "tests/card5/test_option_d_scope_seal_v5.py",
        "evidence/card5_lora_v3_3/api_inventory_v5.json",
        "evidence/card5_lora_v3_3/option_d_manifest_v5.json",
    ]
    for path in required:
        assert Path(path).exists(), path
    print("CARD5_OPTION_D_V5_BACKWARD_COMPAT_FIXTURE_OK=true")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
