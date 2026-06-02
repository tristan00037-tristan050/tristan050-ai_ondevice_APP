from pathlib import Path


def test_box3_package_adds_no_binary_model_or_training_artifacts():
    """본 PR-E v1.2 통합 범위 한정 가드: box3 src + evidence/box3 + box3 tests에
    model binary 0건, training-scope 호출 0건. main의 기존 fixtures/ 등 무관 자산은
    본 PR 책임 외이므로 스캔에서 제외(consumer-only 의도)."""
    root = Path(__file__).resolve().parents[2]
    scan_paths: list[Path] = [
        root / "butler_pc_core/cards/box3",
        root / "evidence/box3",
    ]
    scan_paths += list((root / "tests/connect_loop").glob("test_box3_*.py"))
    forbidden_suffixes = {".safetensors", ".gguf", ".bin", ".pt", ".pth", ".onnx", ".npy", ".pkl"}
    binaries: list[Path] = []
    for sp in scan_paths:
        if not sp.exists():
            continue
        if sp.is_file():
            if sp.suffix in forbidden_suffixes:
                binaries.append(sp)
        else:
            binaries.extend(
                path for path in sp.rglob("*")
                if path.is_file() and path.suffix in forbidden_suffixes
            )
    assert binaries == [], binaries
    source = "\n".join(
        path.read_text(encoding="utf-8")
        for path in (root / "butler_pc_core/cards/box3").rglob("*.py")
    )
    forbidden_calls = ["Trainer(", ".train(", "save_pretrained(", "push_to_hub("]
    for call in forbidden_calls:
        assert call not in source

