from __future__ import annotations
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import argparse, csv, io, json, zipfile

from scripts.ai._aihub_common_v1 import record_zip_inventory, safe_zip_members, write_json


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dataset-dirs", nargs="+", required=True)
    ap.add_argument("--output-dir", required=True)
    ap.add_argument("--sample-count", type=int, default=3)
    args = ap.parse_args()

    out = Path(args.output_dir)
    out.mkdir(parents=True, exist_ok=True)
    inventory = {}
    summary = ["# scouting_summary", ""]

    for ds in args.dataset_dirs:
        p = Path(ds)
        name = p.name
        samples = []
        zip_files = sorted(p.rglob("*.zip"))
        json_files = sorted(p.rglob("*.json")) if not zip_files else []

        if zip_files:
            zf = zip_files[0]
            with zipfile.ZipFile(zf) as z:
                record_zip_inventory(zf, z, inventory)
                for member in safe_zip_members(z):
                    if member.endswith(".json"):
                        with z.open(member) as f:
                            try:
                                obj = json.load(f)
                            except Exception:
                                continue
                        samples.append({"member": member, "sample": obj})
                    elif member.endswith(".tsv"):
                        with z.open(member) as f:
                            txt = f.read().decode("utf-8", errors="ignore")
                        reader = csv.DictReader(io.StringIO(txt), delimiter="\t")
                        for row in reader:
                            samples.append({"member": member, "sample": row})
                            break
                    if len(samples) >= args.sample_count:
                        break
        else:
            for fp in json_files[: args.sample_count]:
                try:
                    obj = json.loads(fp.read_text(encoding="utf-8"))
                except Exception:
                    continue
                samples.append({"member": fp.name, "sample": obj})

        main_fields = sorted({k for s in samples if isinstance(s["sample"], dict) for k in s["sample"].keys()})
        root_format = "tsv" if any(str(s["member"]).endswith(".tsv") for s in samples) else "json"
        report = {
            "dataset_name": name,
            "root_format": root_format,
            "main_fields": main_fields,
            "sample_3": samples[:3],
            "text_candidate_fields": [f for f in main_fields if any(k in f.lower() for k in ("text", "utter", "query", "title", "content", "sentence"))],
            "label_annotation_fields": [],
            "turn_structure": None,
            "event_structure": None,
            "sql_field": None,
            "unusable_reason": None,
        }
        write_json(out / f"{name}.json", report)
        summary += [f"## {name}", f"- root_format: {root_format}", f"- main_fields: {', '.join(main_fields[:20])}", ""]

    write_json(out / "zip_inventory.json", inventory)
    (out / "scouting_summary.md").write_text("\n".join(summary), encoding="utf-8")
    print("SCHEMA_SCOUTING_OK=1")
    print("ZIP_INVENTORY_OK=1")


if __name__ == "__main__":
    main()
