from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping

REQUIRED_FIELDS = ["제목", "발행일", "담당자", "핵심 내용", "합의사항", "금액/일정", "확인 필요", "최종 문안"]
DIGEST_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
RAW_FORBIDDEN_KEYS = {"foreign_doc", "our_format", "reference_text", "expected_output", "raw_text", "source_text", "raw_doc", "input_text"}
STRUCTURED_FACT_RE = re.compile(r"(\d{4}[-./년]\s*\d{1,2}[-./월]\s*\d{0,2}|\d+[,.]?\d*\s*(원|만원|억원|USD|KRW|달러)|[A-Z][a-z]+\s+[A-Z][a-z]+)")

@dataclass(frozen=True)
class EvalSetReport:
    schema_version: str
    eval_set_path: str
    sample_count: int
    digest_only: bool
    source_plaintext_included: bool
    required_fields_ok: bool
    mock_result: bool
    contract_only: bool
    status: str
    invalid_case_ids: list[str]
    def to_dict(self) -> dict[str, Any]: return asdict(self)


def iter_jsonl(path: str | Path) -> Iterable[dict[str, Any]]:
    with Path(path).open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if line.strip():
                try: yield json.loads(line)
                except json.JSONDecodeError as exc: raise ValueError(f"invalid JSONL at line {line_number}: {exc}") from exc


def inspect_eval_set(path: str | Path) -> EvalSetReport:
    rows = list(iter_jsonl(path)); invalid=[]; source_plaintext_included=False; required_fields_ok=True; digest_only=True
    for index, row in enumerate(rows, start=1):
        case_id = str(row.get("case_id", f"line_{index}"))
        if RAW_FORBIDDEN_KEYS.intersection(row.keys()): source_plaintext_included=True; invalid.append(case_id+":source_plaintext_key")
        if row.get("required_fields") != REQUIRED_FIELDS: required_fields_ok=False; invalid.append(case_id+":required_fields")
        for key in ("foreign_doc_digest", "our_format_digest", "semantic_checklist_digest", "format_marker_digest"):
            if not isinstance(row.get(key), str) or not DIGEST_RE.match(row[key]): digest_only=False; invalid.append(case_id+f":{key}")
    status = "PASS_V3_EVAL_SET_CONTRACT" if len(rows) >= 20 and digest_only and not source_plaintext_included and required_fields_ok else "BLOCK_V3_EVAL_SET_CONTRACT"
    return EvalSetReport("box2.helper3.eval_set_report.v3", str(path), len(rows), digest_only, source_plaintext_included, required_fields_ok, False, True, status, invalid)


def _output_mapping(output: Any) -> dict[str, str]:
    if isinstance(output, Mapping): return {str(k): str(v) for k, v in output.items()}
    if isinstance(output, str):
        parsed={}
        for field in REQUIRED_FIELDS:
            match = re.search(rf"(?:^|\n)\s*(?:-\s*)?{re.escape(field)}\s*[:：]\s*(.*)", output)
            if match: parsed[field]=match.group(1).strip()
        return parsed
    return {}


def _call_model_chain(model_chain: Any, case: Mapping[str, Any]) -> dict[str, str]:
    if hasattr(model_chain, "generate_case"): return _output_mapping(model_chain.generate_case(case))
    if hasattr(model_chain, "generate_rewrite"): return _output_mapping(model_chain.generate_rewrite(case))
    if callable(model_chain): return _output_mapping(model_chain(case))
    raise TypeError("model_chain must expose generate_case/generate_rewrite or be callable")


def rewrite_structure_accuracy(output: Mapping[str, str]) -> float:
    keys=list(output.keys()); return sum(1 for i, f in enumerate(REQUIRED_FIELDS) if i < len(keys) and keys[i] == f) / len(REQUIRED_FIELDS)

def required_field_coverage(output: Mapping[str, str], expected_fields: list[str]) -> float:
    return 0.0 if not expected_fields else sum(1 for f in expected_fields if str(output.get(f, "")).strip()) / len(expected_fields)

def unsupported_fact_rate(output: Mapping[str, str], allowed_fact_marker_digests: list[str] | None = None) -> float:
    facts=STRUCTURED_FACT_RE.findall("\n".join(str(v) for v in output.values()))
    if not facts: return 0.0
    return max(0, len(facts)-len(allowed_fact_marker_digests or [])) / len(facts)

def format_match_score(output: Mapping[str, str], expected_markers: list[str]) -> float:
    expected_markers = expected_markers or REQUIRED_FIELDS; keys=list(output.keys())
    return sum(1 for i, m in enumerate(expected_markers) if i < len(keys) and keys[i] == m) / len(expected_markers)

def semantic_preservation_score(output: Mapping[str, str], checklist: list[str]) -> float:
    checklist = checklist or ["has_required_structure", "no_specific_fact_fabrication", "uncertainty_marked", "has_final_text"]
    text="\n".join(output.values())
    checks={"has_required_structure": rewrite_structure_accuracy(output)==1.0, "no_specific_fact_fabrication": unsupported_fact_rate(output)==0.0, "uncertainty_marked": "확인 필요" in text, "has_final_text": bool(str(output.get("최종 문안", "")).strip())}
    return sum(1 for item in checklist if checks.get(item, True)) / len(checklist)


def run_real_eval(model_chain: Any, eval_cases_path: Path) -> dict[str, Any]:
    report=inspect_eval_set(eval_cases_path); rows=list(iter_jsonl(eval_cases_path))
    if report.status != "PASS_V3_EVAL_SET_CONTRACT":
        return {"schema_version":"box2.helper3.eval_real.v3","status":"BLOCK_V3_EVAL_SET_CONTRACT","sample_count":report.sample_count,"mock_result":False,"output_digest_only":True,"raw_output_saved":False,"external_send_zero":True,"raw_persistence_zero":True,"fail_class":"BLOCK_V3_EVAL_SET_CONTRACT","invalid_case_ids":report.invalid_case_ids}
    metric_rows=[]; per_case_digest=[]
    for row in rows:
        output=_call_model_chain(model_chain, row)
        metrics={"rewrite_structure_accuracy": rewrite_structure_accuracy(output), "required_field_coverage": required_field_coverage(output, row.get("expected_required_fields") or REQUIRED_FIELDS), "unsupported_fact_rate": unsupported_fact_rate(output, row.get("allowed_fact_marker_digests") or []), "format_match_score": format_match_score(output, row.get("expected_format_markers") or REQUIRED_FIELDS), "semantic_preservation_score": semantic_preservation_score(output, row.get("semantic_checklist") or [])}
        metric_rows.append(metrics)
        per_case_digest.append({"case_id": row["case_id"], "output_digest": "sha256:" + hashlib.sha256(json.dumps(output, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest(), "metrics": metrics})
    avg=lambda k: round(sum(m[k] for m in metric_rows)/len(metric_rows), 6)
    aggregate={"rewrite_structure_accuracy":avg("rewrite_structure_accuracy"),"required_field_coverage":avg("required_field_coverage"),"unsupported_fact_rate":avg("unsupported_fact_rate"),"format_match_score":avg("format_match_score"),"semantic_preservation_score":avg("semantic_preservation_score")}
    passed=len(rows)>=20 and aggregate["rewrite_structure_accuracy"]>=0.85 and aggregate["required_field_coverage"]>=0.90 and aggregate["unsupported_fact_rate"]<=0.03 and aggregate["format_match_score"]>=0.85 and aggregate["semantic_preservation_score"]>=0.85
    return {"schema_version":"box2.helper3.eval_real.v3","status":"PASS_V2_FULL_METRIC" if passed else "PARTIAL_DONE_V3_EVAL_INSUFFICIENT","sample_count":len(rows),"mock_result":False,"metric_is_digest_safe_proxy":True,"semantic_metric_kind":"digest_safe_checklist_proxy","output_digest_only":True,"raw_output_saved":False,"external_send_zero":True,"raw_persistence_zero":True,"fail_class":None if passed else "PARTIAL_DONE_V3_EVAL_INSUFFICIENT",**aggregate,"per_case_output_digests":per_case_digest}


def write_real_eval_evidence(model_chain: Any, eval_cases_path: Path, evidence_path: Path) -> dict[str, Any]:
    payload=run_real_eval(model_chain, eval_cases_path); evidence_path.parent.mkdir(parents=True, exist_ok=True); evidence_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2)+"\n", encoding="utf-8"); return payload
