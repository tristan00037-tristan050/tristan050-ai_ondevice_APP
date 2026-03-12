from __future__ import annotations

import argparse
import hashlib
import json
import time
from pathlib import Path
from typing import Any


# ---------------------------------------------------------------------------
# 유틸리티
# ---------------------------------------------------------------------------

def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


# ---------------------------------------------------------------------------
# Step 1. SHA256SUMS 무결성 검증
# ---------------------------------------------------------------------------

def verify_sha256sums(pack_dir: Path) -> dict:
    sums_path = pack_dir / "SHA256SUMS"
    if not sums_path.exists():
        raise RuntimeError("SHA256SUMS_MISSING")

    lines = sums_path.read_text(encoding="utf-8").strip().splitlines()
    results = []
    for line in lines:
        parts = line.strip().split("  ", 1)
        if len(parts) != 2:
            raise RuntimeError(f"SHA256SUMS_FORMAT_INVALID: {line}")
        expected_hex, name = parts
        file_path = pack_dir / name
        if not file_path.exists():
            raise RuntimeError(f"SHA256SUMS_FILE_MISSING: {name}")
        actual_hex = sha256_file(file_path)
        if actual_hex != expected_hex:
            raise RuntimeError(
                f"SHA256SUMS_MISMATCH: {name} "
                f"expected={expected_hex[:8]} actual={actual_hex[:8]}"
            )
        results.append({"file": name, "digest": actual_hex, "ok": True})

    print(f"SHA256SUMS_VERIFIED=1 files={len(results)}")
    return {"verified_files": results}


# ---------------------------------------------------------------------------
# Step 2. runtime_manifest 계약 검증
# ---------------------------------------------------------------------------

def verify_runtime_manifest(pack_dir: Path) -> dict:
    manifest_path = pack_dir / "runtime_manifest.json"
    if not manifest_path.exists():
        raise RuntimeError("RUNTIME_MANIFEST_MISSING")

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest_str = json.dumps(manifest)

    # REQUIRED 플레이스홀더 체크
    if "REQUIRED" in manifest_str:
        raise RuntimeError("RUNTIME_MANIFEST_PLACEHOLDER_REMAINING")

    # status 체크 — 반드시 pending_real_weights여야 전환 가능
    status = manifest.get("status")
    if status == "verified":
        raise RuntimeError("ALREADY_VERIFIED: 이미 verified 상태입니다.")
    if status != "pending_real_weights":
        raise RuntimeError(f"UNEXPECTED_STATUS: {status}")

    # 필수 필드 체크
    required_fields = [
        "schema_version", "logical_pack_id", "model_format",
        "quantization_mode", "context_length",
        "bos_token_id", "eos_token_id",
    ]
    for field in required_fields:
        if field not in manifest:
            raise RuntimeError(f"MANIFEST_FIELD_MISSING: {field}")

    # artifacts digest 체크
    arts = manifest.get("artifacts", {})
    for key in ["weights_digest_sha256", "tokenizer_digest_sha256",
                "chat_template_digest_sha256"]:
        if not arts.get(key):
            raise RuntimeError(f"MANIFEST_ARTIFACT_MISSING: {key}")

    print("RUNTIME_MANIFEST_CONTRACT_OK=1")
    return {
        "logical_pack_id": manifest["logical_pack_id"],
        "quantization_mode": manifest["quantization_mode"],
        "context_length": manifest["context_length"],
    }


# ---------------------------------------------------------------------------
# Step 3. SLO 수치 검증
# ---------------------------------------------------------------------------

def verify_slo(pack_dir: Path, tmp_dir: Path, logical_pack_id: str) -> dict:
    # eval 결과 — 팩 전용 파일만 허용 (fallback 금지)
    eval_path = tmp_dir / f"{logical_pack_id}_eval_results.json"
    if not eval_path.exists():
        raise RuntimeError(
            f"EVAL_RESULT_MISSING: {eval_path} "
            f"— 반드시 {logical_pack_id} 전용 eval 결과 파일이 있어야 합니다."
        )

    eval_data = json.loads(eval_path.read_text(encoding="utf-8"))
    schema_pass_rate = eval_data.get("schema_pass_rate", 0)
    if schema_pass_rate < 0.98:
        raise RuntimeError(
            f"SLO_EVAL_FAILED: schema_pass_rate={schema_pass_rate} < 0.98"
        )

    # variance 결과 — 정규 경로 우선, 팩별 경로 보조
    # 정규 경로: measure_runtime_variance_v1.py 출력 경로
    var_path = tmp_dir / "runtime_variance_summary.json"
    if not var_path.exists():
        var_path = tmp_dir / f"runtime_variance_summary_{logical_pack_id}.json"
    if not var_path.exists():
        raise RuntimeError(
            f"VARIANCE_RESULT_MISSING: tmp/runtime_variance_summary.json 또는 "
            f"tmp/runtime_variance_summary_{logical_pack_id}.json 필요"
        )

    var_data = json.loads(var_path.read_text(encoding="utf-8"))

    # SLO 기준 (small_default)
    SLO = {
        "decode_tps_mean": 8.0,
        "rss_max_mb": 3072.0,
        "sample_count": 31,
    }

    tps  = var_data.get("decode_tps_mean", 0)
    rss  = var_data.get("rss_peak_max_mb", var_data.get("rss_max_mb", 9999))
    cnt  = var_data.get("sample_count", 0)

    if tps < SLO["decode_tps_mean"]:
        raise RuntimeError(f"SLO_TPS_FAILED: {tps} < {SLO['decode_tps_mean']}")
    if rss > SLO["rss_max_mb"]:
        raise RuntimeError(f"SLO_RSS_FAILED: {rss} > {SLO['rss_max_mb']}")
    if cnt < SLO["sample_count"]:
        raise RuntimeError(f"SLO_SAMPLE_FAILED: {cnt} < {SLO['sample_count']}")

    print(
        f"SLO_VERIFIED=1 "
        f"tps={tps} rss={rss} samples={cnt} "
        f"schema_pass_rate={schema_pass_rate}"
    )
    return {
        "schema_pass_rate": schema_pass_rate,
        "decode_tps_mean": tps,
        "rss_max_mb": rss,
        "sample_count": cnt,
    }


# ---------------------------------------------------------------------------
# Step 4. verified 전환
# ---------------------------------------------------------------------------

def transition_to_verified(pack_dir: Path) -> None:
    manifest_path = pack_dir / "runtime_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    manifest["status"] = "verified"

    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print("STATUS_TRANSITIONED=verified")


# ---------------------------------------------------------------------------
# Step 5. SHA256SUMS 재생성 (manifest 변경됐으므로)
# ---------------------------------------------------------------------------

def regenerate_sha256sums(pack_dir: Path) -> None:
    files = [
        "model.onnx",
        "tokenizer.json",
        "config.json",
        "chat_template.jinja",
        "runtime_manifest.json",
    ]
    if (pack_dir / "model.onnx.data").exists():
        files.insert(1, "model.onnx.data")

    lines = []
    for name in files:
        p = pack_dir / name
        if not p.exists():
            continue  # 없는 파일은 건너뜀 (가중치 파일 등)
        lines.append(f"{sha256_file(p)}  {name}")

    (pack_dir / "SHA256SUMS").write_text(
        "\n".join(lines) + "\n", encoding="utf-8"
    )
    print("SHA256SUMS_REGENERATED=1")


# ---------------------------------------------------------------------------
# Step 6. 전환 기록 저장
# ---------------------------------------------------------------------------

def write_transition_log(
    pack_dir: Path,
    tmp_dir: Path,
    manifest_info: dict,
    slo_info: dict,
) -> None:
    log = {
        "transition_type": "pending_real_weights_to_verified",
        "transitioned_at_unix": int(time.time()),
        "logical_pack_id": manifest_info["logical_pack_id"],
        "quantization_mode": manifest_info["quantization_mode"],
        "context_length": manifest_info["context_length"],
        "slo_at_transition": slo_info,
        "performed_by": "platform_team",
    }

    tmp_dir.mkdir(exist_ok=True)
    log_path = tmp_dir / f"{manifest_info['logical_pack_id']}_transition_log.json"
    log_path.write_text(
        json.dumps(log, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"TRANSITION_LOG_WRITTEN=1 path={log_path}")


# ---------------------------------------------------------------------------
# 전체 체인 실행
# ---------------------------------------------------------------------------

def run_verified_transition(pack_dir: Path, tmp_dir: Path) -> None:
    print("=" * 60)
    print("VERIFIED TRANSITION CHAIN 시작")
    print("=" * 60)

    # Step 1
    print("\n[1/6] SHA256SUMS 무결성 검증...")
    verify_sha256sums(pack_dir)

    # Step 2
    print("\n[2/6] runtime_manifest 계약 검증...")
    manifest_info = verify_runtime_manifest(pack_dir)

    # Step 3
    print("\n[3/6] SLO 수치 검증...")
    slo_info = verify_slo(pack_dir, tmp_dir, manifest_info["logical_pack_id"])

    # Step 4
    print("\n[4/6] status → verified 전환...")
    transition_to_verified(pack_dir)

    # Step 5
    print("\n[5/6] SHA256SUMS 재생성...")
    regenerate_sha256sums(pack_dir)

    # Step 6
    print("\n[6/6] 전환 기록 저장...")
    write_transition_log(pack_dir, tmp_dir, manifest_info, slo_info)

    print("\n" + "=" * 60)
    print("PACK_VERIFIED_TRANSITION_OK=1")
    print(f"logical_pack_id={manifest_info['logical_pack_id']}")
    print("status=verified")
    print("=" * 60)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="플랫폼팀 전용 — pack verified 전환 체인"
    )
    parser.add_argument("--pack-dir", required=True)
    parser.add_argument("--tmp-dir", default="tmp")
    args = parser.parse_args()

    run_verified_transition(
        pack_dir=Path(args.pack_dir),
        tmp_dir=Path(args.tmp_dir),
    )


if __name__ == "__main__":
    main()
