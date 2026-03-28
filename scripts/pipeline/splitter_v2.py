from __future__ import annotations

import json
import random
from collections import defaultdict
from pathlib import Path


SPLIT_NAMES = ("train", "validation", "test")


class DataSplitter:
    def __init__(self, train: float = 0.9, val: float = 0.05, test: float = 0.05, seed: int = 42):
        total = train + val + test
        if abs(total - 1.0) > 1e-6:
            raise ValueError("split ratios must sum to 1.0")
        self.ratios = (float(train), float(val), float(test))
        self.seed = int(seed)

    @staticmethod
    def _group_by_digest(records: list[dict]) -> list[list[dict]]:
        grouped: dict[str, list[dict]] = {}
        for record in records:
            digest = record.get("output_digest_sha256") or f"missing::{id(record)}"
            grouped.setdefault(digest, []).append(record)
        return list(grouped.values())

    def split(self, records: list[dict], output_dir: str) -> dict:
        rng = random.Random(self.seed)
        by_domain: dict[str, list[dict]] = defaultdict(list)
        for record in records:
            by_domain[record.get("domain", "general")].append(record)

        splits = {name: [] for name in SPLIT_NAMES}
        domain_stats = {}

        for domain, domain_records in by_domain.items():
            groups = self._group_by_digest(domain_records)
            rng.shuffle(groups)

            total_items = len(domain_records)
            total_groups = len(groups)
            target_train = int(total_groups * self.ratios[0])
            target_val = int(total_groups * self.ratios[1])

            train_groups = groups[:target_train]
            validation_groups = groups[target_train : target_train + target_val]
            test_groups = groups[target_train + target_val :]

            for group in train_groups:
                splits["train"].extend(group)
            for group in validation_groups:
                splits["validation"].extend(group)
            for group in test_groups:
                splits["test"].extend(group)

            domain_stats[domain] = {
                "total": total_items,
                "train": sum(len(group) for group in train_groups),
                "validation": sum(len(group) for group in validation_groups),
                "test": sum(len(group) for group in test_groups),
            }

        leakage_count = self._check_leakage(splits)

        out = Path(output_dir)
        out.mkdir(parents=True, exist_ok=True)
        for name, data in splits.items():
            rng.shuffle(data)
            with (out / f"{name}.jsonl").open("w", encoding="utf-8") as fh:
                for record in data:
                    fh.write(json.dumps(record, ensure_ascii=False) + "\n")

        return {
            "counts": {name: len(data) for name, data in splits.items()},
            "domain_stats": domain_stats,
            "leakage_count": leakage_count,
        }

    @staticmethod
    def _check_leakage(splits: dict[str, list[dict]]) -> int:
        train_digests = {
            record.get("output_digest_sha256")
            for record in splits["train"]
            if record.get("output_digest_sha256")
        }
        leakage = 0
        for name in ("validation", "test"):
            for record in splits[name]:
                if record.get("output_digest_sha256") in train_digests:
                    leakage += 1
        return leakage
