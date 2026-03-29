from __future__ import annotations

import hashlib
import json
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional


REQUIRED_FIELDS = {"prompt", "completion", "domain", "case_id", "difficulty", "policy_sensitive"}
ALLOWED_DOMAINS = {"legal", "finance", "medical", "admin", "general"}
MIN_TOTAL = 150
MIN_PER_DOMAIN = 20
MIN_POLICY_SENSITIVE = 30
MAX_DOMAIN_RATIO = 2.0
MAX_DUPLICATE_RATIO = 0.0


@dataclass
class DatasetValidationResult:
    ok: bool
    fail_reasons: List[str]
    total_rows: int
    per_domain: Dict[str, int]
    policy_sensitive_count: int
    duplicate_prompt_ratio: float
    malformed_rows: int
    invalid_rows: int
    leakage_count: int
    dataset_digest: Optional[str] = None
    report: Dict[str, object] = field(default_factory=dict)


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def validate_eval_dataset(eval_file: str, *, train_digest_file: Optional[str] = None) -> DatasetValidationResult:
    path = Path(eval_file)
    fail_reasons: List[str] = []

    if not path.exists():
        return DatasetValidationResult(
            ok=False,
            fail_reasons=["EVAL_DATASET_MISSING"],
            total_rows=0,
            per_domain={},
            policy_sensitive_count=0,
            duplicate_prompt_ratio=1.0,
            malformed_rows=0,
            invalid_rows=0,
            leakage_count=0,
        )

    rows: List[dict] = []
    malformed_rows = 0
    for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            malformed_rows += 1
            fail_reasons.append(f"EVAL_DATASET_JSONL_PARSE:L{lineno}")

    dataset_digest = hashlib.sha256(path.read_bytes()).hexdigest()[:16]
    if malformed_rows > 0:
        return DatasetValidationResult(
            ok=False,
            fail_reasons=fail_reasons,
            total_rows=len(rows),
            per_domain={},
            policy_sensitive_count=0,
            duplicate_prompt_ratio=1.0,
            malformed_rows=malformed_rows,
            invalid_rows=0,
            leakage_count=0,
            dataset_digest=dataset_digest,
        )

    if len(rows) < MIN_TOTAL:
        fail_reasons.append(f"EVAL_DATASET_TOO_SMALL:{len(rows)}<{MIN_TOTAL}")

    per_domain = Counter()
    prompt_counter = Counter()
    case_ids = set()
    duplicate_case_id = 0
    policy_sensitive_count = 0
    pair_digests = set()
    duplicate_pairs = 0
    invalid_rows = 0
    difficulty_counter = Counter()

    for idx, row in enumerate(rows):
        missing = sorted(REQUIRED_FIELDS - set(row.keys()))
        if missing:
            invalid_rows += 1
            fail_reasons.append(f"EVAL_DATASET_SCHEMA:row{idx}:missing={','.join(missing)}")
            continue

        prompt = str(row["prompt"]).strip()
        completion = str(row["completion"]).strip()
        case_id = str(row["case_id"]).strip()
        difficulty = str(row["difficulty"]).strip()
        domain = str(row["domain"]).strip()

        if not prompt or not completion or not case_id or not difficulty:
            invalid_rows += 1
            fail_reasons.append(f"EVAL_DATASET_MALFORMED_RECORD:row{idx}")
            continue

        if domain not in ALLOWED_DOMAINS:
            invalid_rows += 1
            fail_reasons.append(f"EVAL_DATASET_DOMAIN_UNKNOWN:{domain}")
            continue

        per_domain[domain] += 1
        difficulty_counter[difficulty] += 1

        if not isinstance(row["policy_sensitive"], bool):
            invalid_rows += 1
            fail_reasons.append(f"EVAL_DATASET_SCHEMA:row{idx}:policy_sensitive_not_bool")
            continue

        if row["policy_sensitive"] is True:
            policy_sensitive_count += 1

        prompt_norm = " ".join(prompt.split())
        prompt_counter[prompt_norm] += 1

        if case_id in case_ids:
            duplicate_case_id += 1
        case_ids.add(case_id)

        pair_digest = _sha256_text(prompt_norm + "\n" + completion)
        if pair_digest in pair_digests:
            duplicate_pairs += 1
        pair_digests.add(pair_digest)

    for domain in ALLOWED_DOMAINS:
        if per_domain[domain] < MIN_PER_DOMAIN:
            fail_reasons.append(f"EVAL_DATASET_DOMAIN_COUNT_{domain.upper()}:{per_domain[domain]}<{MIN_PER_DOMAIN}")

    if policy_sensitive_count < MIN_POLICY_SENSITIVE:
        fail_reasons.append(f"EVAL_DATASET_POLICY_COVERAGE:{policy_sensitive_count}<{MIN_POLICY_SENSITIVE}")

    duplicate_prompt_count = sum(count - 1 for count in prompt_counter.values() if count > 1)
    duplicate_prompt_ratio = duplicate_prompt_count / max(len(rows), 1)
    if duplicate_prompt_ratio > MAX_DUPLICATE_RATIO:
        fail_reasons.append(f"EVAL_DATASET_DUPLICATE_PROMPT:{duplicate_prompt_ratio:.3f}")

    if duplicate_case_id > 0:
        fail_reasons.append(f"EVAL_DATASET_DUPLICATE_CASE_ID:{duplicate_case_id}")

    leakage_count = duplicate_pairs
    if leakage_count > 0:
        fail_reasons.append(f"EVAL_DATASET_LEAKAGE:{leakage_count}")

    counts = [per_domain[d] for d in ALLOWED_DOMAINS if per_domain[d] > 0]
    ratio = None
    if counts:
        ratio = max(counts) / min(counts)
        if ratio > MAX_DOMAIN_RATIO:
            fail_reasons.append(f"EVAL_DATASET_DOMAIN_IMBALANCE:{ratio:.3f}")

    external_train_overlap = 0
    if train_digest_file:
        digest_path = Path(train_digest_file)
        if digest_path.exists():
            train_digests = {line.strip() for line in digest_path.read_text(encoding="utf-8").splitlines() if line.strip()}
            for row in rows:
                prompt_norm = " ".join(str(row.get("prompt", "")).split())
                if row.get("case_id") in train_digests or _sha256_text(prompt_norm) in train_digests:
                    external_train_overlap += 1
            if external_train_overlap > 0:
                fail_reasons.append(f"EVAL_DATASET_TRAIN_LEAKAGE:{external_train_overlap}")

    ok = len(fail_reasons) == 0
    return DatasetValidationResult(
        ok=ok,
        fail_reasons=fail_reasons,
        total_rows=len(rows),
        per_domain=dict(per_domain),
        policy_sensitive_count=policy_sensitive_count,
        duplicate_prompt_ratio=duplicate_prompt_ratio,
        malformed_rows=malformed_rows,
        invalid_rows=invalid_rows,
        leakage_count=leakage_count + external_train_overlap,
        dataset_digest=dataset_digest,
        report={
            "domain_ratio": ratio,
            "duplicate_prompt_count": duplicate_prompt_count,
            "duplicate_case_id": duplicate_case_id,
            "duplicate_pairs": duplicate_pairs,
            "external_train_overlap": external_train_overlap,
            "difficulty_counts": dict(difficulty_counter),
            "safety_or_adversarial_count": policy_sensitive_count,
        },
    )
